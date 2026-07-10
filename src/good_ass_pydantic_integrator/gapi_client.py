# TODO: Validate
"""Abstract base client for auto-generating and validating Pydantic models."""

import importlib
import inspect
import json
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, cast, overload

from pydantic import BaseModel, RootModel, ValidationError

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
root, not the ``base_model`` submodule), so they carry raw input."""


def _recover_raw_input(value: object) -> JSON_VALUE:
    """Recover the raw input a model (or container of models) was built from.

    Object models are :class:`GAPIBaseModel` and record their raw input
    directly. A root model (e.g. a top-level JSON list) is a ``RootModel`` that
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

    _discriminator_key: str | None = None
    """Key to use for creating discriminated unions (e.g. ``"__typename"`` for graphql
    endpoints.)"""

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
    def clean_data(cls, data: INPUT_TYPE) -> INPUT_TYPE:
        """Transform raw input before validation and before model generation.

        The default is a no-op. Override in a subclass to reshape the raw
        downloaded data (e.g. denormalize an Apollo cache into per-type lists)
        without changing what is stored on disk: the saved JSON corpus stays
        exactly as downloaded, and this hook runs on the way into both
        ``parse`` and model rebuilding, so the two never drift apart.

        Args:
            data: The raw JSON data, as downloaded/saved.

        Returns:
            The transformed data to validate and to build the schema from.
        """
        return data

    @classmethod
    def _modified_object_from_file(cls, file_path: Path) -> INPUT_TYPE:
        """Load a saved raw JSON file and apply ``clean_data`` to it."""
        return cls.clean_data(json.loads(file_path.read_text()))

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

    @staticmethod
    def _folder_name(model_name: str) -> str:
        """Convert a model class name to snake_case for the folder name."""
        string = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", model_name)
        string = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", string)
        return string.lower().removesuffix("_model")

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
        model_path = cls._model_path()
        folder_name = cls._folder_name(cls._model_name())
        return model_path.parent.parent / "_files" / folder_name

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
        that re-serialization would lose (e.g. a datetime's original ``Z`` suffix).
        Use ``model_dump`` instead to get the model's own serialized shape.

        Args:
            data: A model instance or sequence of model instances.

        Returns:
            The raw input, or a list of raw inputs for a sequence.

        Raises:
            ValueError: If a model has no recorded raw input (i.e. it was built
                via ``model_construct`` rather than validated).
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

        Unlike ``original_input``, which returns the exact validated input, this
        reflects the model's current field values, re-serialized by Pydantic. Uses
        ``mode="json"`` for JSON-compatible values, ``by_alias=True`` so field
        aliases match the source shape, and ``exclude_unset=True`` to omit fields
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
    def parse(cls, data: INPUT_TYPE, *, update_model: bool = True) -> T:
        """Parses data into a model.

        Args:
            data: The data to parse.
            update_model: Whether to update the model if parsing fails.

        Returns:
            A model instance containing the parsed data.
        """
        try:
            return cls._response_model.model_validate(
                data,
                context={MODIFIER_CONTEXT_KEY: cls.clean_data},
            )
        # If validation fails and updating is allowed, try automatically rebuilding
        # and reloading the model using the new data, then validate again. A second
        # failure raises an error that must be handled manually.
        except ValidationError:
            if not update_model:
                raise
            logger.info("Validation failed: %s.", cls._model_name())
            new_file = cls.save_new_json_file(data)
            cls._update_model(new_file)
            return cls._response_model.model_validate(
                data,
                context={MODIFIER_CONTEXT_KEY: cls.clean_data},
            )

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
                discriminator_key=cls._discriminator_key,
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
            discriminator_key=cls._discriminator_key,
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
        """Create ``__init__.py`` in the model directory if it doesn't exist."""
        model_path = cls._model_path()
        init_path = model_path.parent / "__init__.py"
        if not init_path.exists():
            init_path.write_text(f'"""Models for {cls._model_name()}."""')
