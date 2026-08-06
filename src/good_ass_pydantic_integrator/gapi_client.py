# TODO: Validate
"""Abstract base client for auto-generating and validating Pydantic models."""

import importlib
import inspect
import json
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import IntEnum
from logging import getLogger
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    Union,
    cast,
    get_args,
    get_origin,
    overload,
)

from pydantic import BaseModel, RootModel, ValidationError, create_model
from pydantic.fields import FieldInfo

from good_ass_pydantic_integrator.base_model import (
    MODIFIER_CONTEXT_KEY,
    GAPIBaseModel,
)
from good_ass_pydantic_integrator.constants import BLANK_MODEL_TEMPLATE
from good_ass_pydantic_integrator.customizer import (
    CustomSerializer,
    GAPICustomizer,
    ReplacementField,
    ReplacementType,
)
from good_ass_pydantic_integrator.gapi import GAPI

if TYPE_CHECKING:
    from good_ass_pydantic_integrator.constants import INPUT_TYPE, JSON_VALUE


logger = getLogger(__name__)

_GAPI_MODEL_BASE_CLASS = f"good_ass_pydantic_integrator.{GAPIBaseModel.__qualname__}"
"""Public dotted path generated response models inherit from (via the package
root, not the `base_model` submodule), so they carry raw input."""


class ParseLevel(IntEnum):
    """How far `GAPIClient.parse` may go to make invalid data parse.

    Each level adds one recovery stage to the one below it, so a higher level
    always tries everything a lower level does first.
    """

    STRICT = 1
    """Validate once. A failure raises, leaving the model untouched."""

    UPDATE = 2
    """Also save the data as a new sample, update the model from it, and
    validate again. This is the default."""

    ALLOW_EXTRA = 3
    """Also validate again with the generated models' `extra="forbid"`
    overridden, so unknown fields are ignored rather than rejected."""

    ALLOW_MISSING = 4
    """Also validate a final time against a throwaway subclass of the response
    model with every field, at every level of nesting, made optional. The data is
    still validated, coerced and parsed into nested models as usual, but a field
    the data no longer carries comes back as `None` even though its type hint
    says it cannot be. The result is typed as the response model, so this hides a
    real mismatch from callers: use it where a partial model beats no model."""


type _OPTIONAL_MEMO = dict[type[BaseModel], type[BaseModel]]


def _optional_annotation(annotation: Any, memo: _OPTIONAL_MEMO) -> Any:  # noqa: ANN401 - An annotation can be anything.
    """Rewrite an annotation so every model nested inside it is made optional.

    Containers are rebuilt from their rewritten arguments, so a model reached
    through a `list`, a union, a `dict` value or an `Annotated` is relaxed too.
    Anything that is not a model and holds no models is returned unchanged.
    """
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _optional_model(annotation, memo)

    origin = get_origin(annotation)
    if origin is None:
        return annotation

    arguments = get_args(annotation)
    if origin is Annotated:
        annotated, *metadata = arguments
        return Annotated[(_optional_annotation(annotated, memo), *metadata)]

    rewritten = tuple(_optional_annotation(argument, memo) for argument in arguments)
    # `X | Y` cannot be rebuilt by subscripting its origin, unlike every other
    # container, so it is rebuilt through `Union` instead.
    if origin is Union:
        return Union[rewritten]  # noqa: UP007 - Subscripted with a tuple of types.
    return origin[rewritten]


def _optional_model(model: type[BaseModel], memo: _OPTIONAL_MEMO) -> type[BaseModel]:
    """Return a subclass of `model` with every field optional, recursively.

    Fields keep their aliases, constraints and validators, so the data is parsed
    exactly as it normally would be. Only two things change: a missing field
    defaults to `None` instead of failing, and extra fields are ignored, since a
    model that tolerates missing fields but not unknown ones would be a strange
    half-measure at the point this is used.
    """
    cached = memo.get(model)
    if cached is not None:
        return cached

    # Created empty and memoized before the fields are rewritten so a model that
    # refers to itself, directly or through another model, resolves to this class
    # instead of recursing forever.
    optional = create_model(f"{model.__name__}Optional", __base__=model)
    memo[model] = optional

    for name, field in model.model_fields.items():
        annotation = _optional_annotation(field.annotation, memo)
        optional.model_fields[name] = FieldInfo.merge_field_infos(
            field,
            annotation=annotation | None,
            default=None,
        )

    # A subclass gets its own `model_config` dict, so this leaves the response
    # model, which the rest of the client keeps using, strict.
    optional.model_config["extra"] = "ignore"
    optional.model_rebuild(force=True)
    return optional


def _recover_raw_input(value: object) -> JSON_VALUE:
    """Recover the raw input a model (or container of models) was built from.

    Object models are :class:`GAPIBaseModel` and record their raw input
    directly. A root model (e.g. a top-level JSON list) is a `RootModel` that
    records nothing itself, so its raw input is rebuilt from the models it wraps.
    Plain JSON values pass through unchanged.
    """
    if isinstance(value, RootModel):
        # reportUnknownMemberType - RootModel.root is the unparametrized generic.
        root = cast("object", value.root)  # type: ignore[reportUnknownMemberType]
        return _recover_raw_input(root)
    if isinstance(value, GAPIBaseModel):
        return value.raw_input
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence):
        return [_recover_raw_input(item) for item in cast("Sequence[object]", value)]
    return cast("JSON_VALUE", value)


class GAPIClient[T: BaseModel]:
    """Base class for API endpoints to auto-generate Pydantic models from responses."""

    _response_model: type[T]
    """The Pydantic model class for this client. Must be set by subclasses."""

    JSON_FILES_ROOT: ClassVar[Path | None] = None
    """Root directory for saved JSON files. Each model's files live in
    `JSON_FILES_ROOT / <ClassName> / <file>.json`. When `None` (the default),
    the root is a `json_files` directory next to the subclass that defines the
    client. Override in a subclass to relocate all saved files."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Validate that subclasses define _response_model correctly."""
        super().__init_subclass__(**kwargs)
        if "_response_model" in cls.__dict__:
            model = cls.__dict__["_response_model"]
            # A response model is either an object model (GAPIBaseModel, which
            # records raw input) or a root model (RootModel, e.g. a top-level
            # list, whose raw input is recovered from the models it wraps).
            if not (
                isinstance(model, type)
                and issubclass(model, (GAPIBaseModel, RootModel))
            ):
                msg = (
                    f"{cls.__name__}._response_model must be a GAPIBaseModel or "
                    f"RootModel subclass, got {model!r}"
                )
                raise TypeError(msg)

    @classmethod
    def transform_input(cls, data: INPUT_TYPE) -> INPUT_TYPE:
        """Transform raw input before validation and before model generation.

        The default is a no-op. Override in a subclass to reshape the raw
        downloaded data (e.g. denormalize an Apollo cache into per-type lists)
        without changing what is stored on disk: the saved JSON corpus stays
        exactly as downloaded, and this hook runs on the way into both
        `parse` and model rebuilding, so the two never drift apart.

        Args:
            data: The raw JSON data, as downloaded/saved.

        Returns:
            The transformed data to validate and to build the schema from.
        """
        return data

    @classmethod
    def _modified_object_from_file(cls, file_path: Path) -> INPUT_TYPE:
        """Load a saved raw JSON file and apply `transform_input` to it."""
        return cls.transform_input(json.loads(file_path.read_text()))

    @classmethod
    def _replacement_fields(cls) -> list[ReplacementField]:
        """Return field replacements for the generated model."""
        return []

    @classmethod
    def _replacement_types(cls) -> list[ReplacementType]:
        """Return type replacements for the generated model."""
        return []

    @classmethod
    def _custom_serializers(cls) -> list[CustomSerializer]:
        """Return custom serializers for the generated model."""
        return []

    @classmethod
    def _additional_imports(cls) -> list[str]:
        """Return additional import lines for the generated model."""
        return []

    @classmethod
    def _customizer(cls) -> GAPICustomizer:
        """Return a customizer from the configured fields, serializers, and imports."""
        customizer = GAPICustomizer()
        customizer.replacement_fields = cls._replacement_fields()
        customizer.replacement_types = cls._replacement_types()
        customizer.custom_serializers = cls._custom_serializers()
        customizer.additional_imports = cls._additional_imports()
        return customizer

    @classmethod
    def _model_name(cls) -> str:
        """Return the name of the response model class."""
        return cls._response_model.__name__

    @classmethod
    def _model_path(cls) -> Path:
        """Return the file path for the response model."""
        return Path(inspect.getfile(cls._response_model))

    @classmethod
    def _schema_path(cls) -> Path:
        """Return the JSON schema file path for the response model."""
        return cls._model_path().with_suffix(".json")

    @classmethod
    def json_files_folder(cls) -> Path:
        """Return the folder that contains all saved JSON files for the model."""
        root = cls.JSON_FILES_ROOT
        if root is None:
            return Path(inspect.getfile(cls)).parent / "_files"
        return root / cls._model_name()

    @classmethod
    def json_files(cls) -> list[Path]:
        """Return all saved JSON files for the model, sorted by name."""
        folder = cls.json_files_folder()
        return sorted(folder.glob("*.json"), key=lambda f: f.name)

    @overload
    @staticmethod
    def original_input(data: Sequence[BaseModel]) -> list[INPUT_TYPE]: ...
    @overload
    @staticmethod
    def original_input(data: BaseModel) -> INPUT_TYPE: ...
    @staticmethod
    def original_input(
        data: BaseModel | Sequence[BaseModel],
    ) -> INPUT_TYPE | list[INPUT_TYPE]:
        """Return the exact input a model was created from.

        Handles a single model, a sequence of models, and a root model (e.g. a
        top-level JSON list), recovering the exact raw input in each case. The
        result is verbatim what was validated, so round-tripping preserves details
        that re-serialization would lose (e.g. a datetime's original `Z` suffix).
        Use `model_dump` instead to get the model's own serialized shape.

        Args:
            data: A model instance or sequence of model instances.

        Returns:
            The raw input, or a list of raw inputs for a sequence.

        Raises:
            ValueError: If a model has no recorded raw input (i.e. it was built
                via `model_construct` rather than validated).
        """
        return cast("INPUT_TYPE | list[INPUT_TYPE]", _recover_raw_input(data))

    @overload
    @staticmethod
    def model_dump(data: Sequence[BaseModel]) -> list[INPUT_TYPE]: ...
    @overload
    @staticmethod
    def model_dump(data: BaseModel) -> INPUT_TYPE: ...
    @staticmethod
    def model_dump(
        data: BaseModel | Sequence[BaseModel],
    ) -> INPUT_TYPE | list[INPUT_TYPE]:
        """Serialize a model to a JSON-compatible structure via Pydantic.

        Unlike `original_input`, which returns the exact validated input, this
        reflects the model's current field values, re-serialized by Pydantic. Uses
        `mode="json"` for JSON-compatible values, `by_alias=True` so field
        aliases match the source shape, and `exclude_unset=True` to omit fields
        that were never set.

        Args:
            data: A model instance or sequence of model instances to serialize.

        Returns:
            The serialized model, or a list of serialized models for a sequence.
        """
        if isinstance(data, BaseModel):
            return cast(
                "INPUT_TYPE",
                data.model_dump(mode="json", by_alias=True, exclude_unset=True),
            )
        return [GAPIClient.model_dump(item) for item in data]

    @classmethod
    def _validate(cls, data: INPUT_TYPE, model: type[T] | None = None) -> T:
        """Validate data against the response model, or `model` if given.

        The context is rebuilt per call because the base model pops the modifier
        key out of it while validating.
        """
        return (model or cls._response_model).model_validate(
            data,
            context={MODIFIER_CONTEXT_KEY: cls.transform_input},
        )

    @classmethod
    def _optional_response_model(cls) -> type[T]:
        """Return a subclass of the response model with every field optional.

        It is built on demand rather than cached because the response model is
        replaced by a new class every time it is regenerated. The result is typed
        as the response model, which it is a subclass of, even though a field the
        data omits will hold `None` against what its type hint promises.
        """
        return cast("type[T]", _optional_model(cls._response_model, {}))

    @classmethod
    def _generated_models(cls) -> list[type[BaseModel]]:
        """Return every model class defined in the response model's module."""
        module = sys.modules[cls._response_model.__module__]
        return [
            value
            for value in vars(module).values()
            if isinstance(value, type)
            and issubclass(value, BaseModel)
            and value.__module__ == module.__name__
        ]

    @classmethod
    @contextmanager
    def _extra_fields_allowed(cls) -> Iterator[None]:
        """Temporarily override `extra="forbid"` on the generated models.

        Every model in the generated module is switched to `extra="ignore"` and
        rebuilt for the duration of the block, then restored to exactly the
        config it had before.
        """
        originals = [
            (model, model.model_config.get("extra"))
            for model in cls._generated_models()
        ]
        try:
            for model, _ in originals:
                model.model_config["extra"] = "ignore"
                model.model_rebuild(force=True)
            yield
        finally:
            for model, extra in originals:
                if extra is None:
                    model.model_config.pop("extra", None)
                else:
                    model.model_config["extra"] = extra
                model.model_rebuild(force=True)

    @classmethod
    def parse(cls, data: INPUT_TYPE, *, level: ParseLevel = ParseLevel.UPDATE) -> T:
        """Parses data into a model, recovering from failures up to `level`.

        The stages, each only attempted when `level` allows it, are:

        1. Validate the data as-is (`ParseLevel.STRICT`).
        2. Save the data as a new sample, update the model from it, and validate
           again (`ParseLevel.UPDATE`).
        3. Validate again with `extra="forbid"` overridden on the generated
           models, so unknown fields are ignored (`ParseLevel.ALLOW_EXTRA`).
        4. Validate a final time against a copy of the model with every field
           made optional (`ParseLevel.ALLOW_MISSING`).

        Data that fails the first stage is saved as a new sample either way, so
        anything that only parses at a later stage is on disk to look at later.

        Args:
            data: The data to parse.
            level: How far to go to make the data parse. The failure of the last
                stage the level permits is raised.

        Returns:
            A model instance containing the parsed data.

        Raises:
            ValidationError: If the data still fails to validate after every
                stage `level` permits.
        """
        try:
            return cls._validate(data)
        except ValidationError:
            if level < ParseLevel.UPDATE:
                raise
            logger.info("Validation failed: %s.", cls._model_name())
            cls._update_model(cls.save_new_json_file(data))

        try:
            return cls._validate(data)
        except ValidationError:
            if level < ParseLevel.ALLOW_EXTRA:
                raise
            logger.info("Validation failed after updating: %s.", cls._model_name())

        # The updated model still rejects the data, so the mismatch is not just a
        # field the schema has not seen yet. Ignoring unknown fields shows whether
        # extra fields alone are the problem, and salvages the parse if they are.
        try:
            with cls._extra_fields_allowed():
                return cls._validate(data)
        except ValidationError:
            if level < ParseLevel.ALLOW_MISSING:
                raise
            logger.info(
                "Validation failed allowing extra fields: %s.",
                cls._model_name(),
            )

        logger.warning(
            "Parsing %s with every field optional. Fields the data is missing "
            "will be None despite what their type hints say.",
            cls._model_name(),
        )
        return cls._validate(data, cls._optional_response_model())

    @classmethod
    def rebuild_model(cls) -> None:
        """Rebuild the schema and model using the saved files.

        Returns:
            The reloaded model class.
        """
        if cls.json_files():
            logger.info("Rebuilding model %s.", cls._model_name())
            gapi = GAPI(
                cls._model_name(),
                customizer=cls._customizer(),
                base_class=_GAPI_MODEL_BASE_CLASS,
            )
            for json_file in cls.json_files():
                gapi.add_object_from_dict(cls._modified_object_from_file(json_file))
            gapi.write_json_schema_to_file(cls._schema_path())
            gapi.write_pydantic_model_to_file(cls._model_path())
            cls._create_init_file()
        else:
            cls.write_blank_model()

        cls._reload_model()

    @classmethod
    def write_blank_model(cls) -> None:
        """Replace the existing model and schema with blank template files.

        The schema file will be deleted, and the model will be overwritten with a
        template that contains no fields.

        Returns:
            The reloaded model class.
        """
        logger.info("Writing blank model: %s.", cls._model_name())
        content = BLANK_MODEL_TEMPLATE.format(class_name=cls._model_name())
        cls._model_path().write_text(content)
        if cls._schema_path().exists():
            cls._schema_path().unlink()
        cls._reload_model()

    @classmethod
    def remove_redundant_json_files(cls) -> None:
        """Remove JSON files that are redundant for schema generation."""
        logger.info("Checking for redundant JSON files: %s.", cls._model_name())
        # Check the newest files first so files should only change when actually
        # required.
        input_files = cls.json_files()
        input_files.reverse()

        gapi = GAPI()
        for file in input_files:
            gapi.add_object_from_dict(cls._modified_object_from_file(file))
        complete_schema = gapi.builder

        i = 0
        while i < len(input_files):
            test_files = input_files[:i] + input_files[i + 1 :]
            gapi = GAPI()
            for file in test_files:
                gapi.add_object_from_dict(cls._modified_object_from_file(file))
            if gapi.builder == complete_schema:
                logger.info("Deleting redundant JSON file: %s", input_files[i].name)
                input_files[i].unlink()
                input_files.pop(i)
            else:
                i += 1

    @classmethod
    def _update_model(cls, new_file_path: Path) -> None:
        """Update the schema and model with new data.

        Args:
            new_file_path: Path to a JSON file containing the new data.
        """
        logger.info("Updating model %s.", cls._model_name())
        gapi = GAPI(
            cls._model_name(),
            customizer=cls._customizer(),
            base_class=_GAPI_MODEL_BASE_CLASS,
        )
        if cls._schema_path().exists():
            gapi.add_schema_from_file(cls._schema_path())
        gapi.add_object_from_dict(cls._modified_object_from_file(new_file_path))
        gapi.write_json_schema_to_file(cls._schema_path())
        gapi.write_pydantic_model_to_file(cls._model_path())
        cls._reload_model()

    @classmethod
    def _reload_model(cls) -> None:
        """Reload the response model by reimporting its module.

        Returns:
            The reloaded model class.
        """
        response_model = cls._response_model
        module = sys.modules[response_model.__module__]

        if hasattr(module, "__cached__") and module.__cached__:
            cached_path = Path(module.__cached__)
            if cached_path.exists():
                cached_path.unlink()

        reloaded_module = importlib.reload(module)
        cls._response_model = getattr(reloaded_module, response_model.__name__)

    @classmethod
    def save_new_json_file(cls, data: INPUT_TYPE) -> Path:
        """Save response data as a JSON file for future model rebuilds."""
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H_%M_%S.%f")[:-3]
        json_path = cls.json_files_folder() / f"{timestamp}.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(data, indent=2))
        logger.info("Saved JSON file: %s.", json_path)
        return json_path

    @classmethod
    def _create_init_file(cls) -> None:
        """Create `__init__.py` in the model directory if it doesn't exist."""
        model_path = cls._model_path()
        init_path = model_path.parent / "__init__.py"
        if not init_path.exists():
            init_path.write_text(f'"""Models for {cls._model_name()}."""')
