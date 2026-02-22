"""Abstract base client for auto-generating and validating Pydantic models."""

import importlib
import inspect
import json
import re
import sys
from datetime import UTC, datetime
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, overload

from pydantic import BaseModel, ValidationError

from good_ass_pydantic_integrator.constants import BLANK_MODEL_TEMPLATE
from good_ass_pydantic_integrator.customizer import (
    CustomSerializer,
    GAPICustomizer,
    ReplacementField,
    ReplacementType,
)
from good_ass_pydantic_integrator.gapi import GAPI

if TYPE_CHECKING:
    from collections.abc import Sequence

    from good_ass_pydantic_integrator.constants import INPUT_TYPE


logger = getLogger(__name__)


class GAPIClient[T: BaseModel]:
    """Base class for API endpoints to auto-generate Pydantic models from responses."""

    _response_model: type[T]
    """The Pydantic model class for this client. Must be set by subclasses."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Validate that subclasses define _response_model correctly."""
        super().__init_subclass__(**kwargs)
        if "_response_model" in cls.__dict__:
            model = cls.__dict__["_response_model"]
            if not (isinstance(model, type) and issubclass(model, BaseModel)):
                msg = (
                    f"{cls.__name__}._response_model must be a BaseModel subclass, "
                    f"got {model!r}"
                )
                raise TypeError(msg)

    # region Customizations

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

    # endregion Customizations

    # region Derived paths

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
    def _get_model_name(cls) -> str:
        """Return the name of the response model class."""
        return cls._response_model.__name__

    @staticmethod
    def _to_folder_name(model_name: str) -> str:
        """Convert a model class name to snake_case for the folder name."""
        string = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", model_name)
        string = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", string)
        return string.lower().removesuffix("_model")

    @classmethod
    def _get_model_path(cls) -> Path:
        """Return the file path for the response model."""
        return Path(inspect.getfile(cls._response_model))

    @classmethod
    def _get_schema_path(cls) -> Path:
        """Return the JSON schema file path for the response model."""
        return cls._get_model_path().with_suffix(".json")

    @classmethod
    def json_files_folder(cls) -> Path:
        """Return the folder that contains all saved JSON files for the model."""
        model_path = cls._get_model_path()
        folder_name = cls._to_folder_name(cls._get_model_name())
        return model_path.parent / "_files" / folder_name

    @classmethod
    def json_files(cls) -> list[Path]:
        """Return all saved JSON files for the model, sorted by name."""
        folder = cls.json_files_folder()
        return sorted(folder.glob("*.json"), key=lambda f: f.name)

    # endregion Derived paths

    # region Public methods

    @overload
    @staticmethod
    def dump_response(data: Sequence[BaseModel]) -> list[dict[str, Any]]: ...
    @overload
    @staticmethod
    def dump_response(data: BaseModel) -> dict[str, Any]: ...
    @staticmethod
    def dump_response(
        data: BaseModel | Sequence[BaseModel],
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Serialize a model instance to a JSON-compatible dict.

        Args:
            data: A model instance or sequence of model instances to serialize.

        Returns:
            A dict or list of dicts representing the serialized model data.
        """
        if isinstance(data, BaseModel):
            return data.model_dump(mode="json", by_alias=True, exclude_unset=True)

        return [GAPIClient.dump_response(item) for item in data]

    @classmethod
    def parse(cls, data: INPUT_TYPE, *, update_model: bool = True) -> T:
        """Parses data into a model.

        Args:
            data: The data to parse.
            update_model: Whether to update the model if parsing fails.

        Returns:
            A model instance containing the parsed data.
        """
        if update_model:
            return cls._parse_and_validate(data)

        return cls._response_model.model_validate(data)

    @classmethod
    def rebuild_model(cls) -> None:
        """Rebuild the schema and model from all saved files.

        Returns:
            The reloaded model class.
        """
        if cls.json_files():
            logger.info("Rebuilding model %s.", cls._get_model_name())
            gapi = GAPI(cls._get_model_name(), customizer=cls._customizer())
            gapi.add_objects_from_folder(cls.json_files_folder())
            gapi.write_json_schema_to_file(cls._get_schema_path())
            gapi.write_pydantic_model_to_file(cls._get_model_path())
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
        logger.info("Writing blank model: %s.", cls._get_model_name())
        content = BLANK_MODEL_TEMPLATE.format(class_name=cls._get_model_name())
        cls._get_model_path().write_text(content)
        if cls._get_schema_path().exists():
            cls._get_schema_path().unlink()
        cls._reload_model()

    @classmethod
    def remove_redundant_json_files(cls) -> None:
        """Remove JSON files that are redundant for schema generation."""
        logger.info("Checking for redundant JSON files: %s.", cls._get_model_name())
        # Check the newest files first so files should only change when actually
        # required.
        input_files = cls.json_files()
        input_files.reverse()

        gapi = GAPI()
        for file in input_files:
            gapi.add_object_from_file(file)
        complete_schema = gapi.builder

        i = 0
        while i < len(input_files):
            test_files = input_files[:i] + input_files[i + 1 :]
            gapi = GAPI()
            for file in test_files:
                gapi.add_object_from_file(file)
            if gapi.builder == complete_schema:
                logger.info("Deleting redundant JSON file: %s", input_files[i].name)
                input_files[i].unlink()
                input_files.pop(i)
            else:
                i += 1

    # endregion Public methods

    # region Private methods

    @classmethod
    def _parse_and_validate(cls, data: INPUT_TYPE) -> T:
        """Validate data against the response model, auto-updating on failure.

        Args:
            data: The raw API response data.

        Returns:
            The validated model instance.
        """
        try:
            parsed = cls._response_model.model_validate(data)
        # If validation fails try automatically rebuilding and reloading the model
        # using the new data and see if validation will succeed with the updated model.
        except ValidationError:
            logger.info("Validation failed: %s.", cls._get_model_name())
            new_file = cls._save_new_json_file(data)
            cls._update_model(new_file)

            # If validation fails a second time this will raise an error that must be
            # handled manually.
            parsed = cls._response_model.model_validate(data)

        # If the dumped response does not match the original input then there is an
        # issue with the parsing or dumping logic that needs to be manually fixed.
        dumped = cls.dump_response(parsed)
        if dumped != data:
            cls._save_debug_files(data, dumped)
            msg = "Parsed response does not match original response."
            raise ValueError(msg)

        return parsed

    @classmethod
    def _update_model(cls, new_file_path: Path) -> None:
        """Update the schema and model with new data.

        Args:
            new_file_path: Path to a JSON file containing the new data.
        """
        logger.info("Updating model %s.", cls._get_model_name())
        gapi = GAPI(cls._get_model_name(), customizer=cls._customizer())
        if cls._get_schema_path().exists():
            gapi.add_schema_from_file(cls._get_schema_path())
        gapi.add_object_from_file(new_file_path)
        gapi.write_json_schema_to_file(cls._get_schema_path())
        gapi.write_pydantic_model_to_file(cls._get_model_path())
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
    def _save_new_json_file(cls, data: INPUT_TYPE) -> Path:
        """Save response data as a JSON file for future model rebuilds."""
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H_%M_%S.%f")[:-3]
        json_path = cls.json_files_folder() / f"{timestamp}.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(data, indent=2))
        logger.info("Saved JSON file: %s.", json_path)
        return json_path

    @classmethod
    def _save_debug_files(cls, data: INPUT_TYPE, dumped: INPUT_TYPE) -> None:
        """Save original and parsed data for debugging round-trip mismatches."""
        cls._save_new_json_file(data)
        folder_name = cls._to_folder_name(cls._get_model_name())
        debug_path = cls._get_model_path().parent / "_files" / "_temp" / folder_name
        debug_path.mkdir(parents=True, exist_ok=True)
        (debug_path / "original.json").write_text(json.dumps(data, indent=2))
        (debug_path / "parsed.json").write_text(json.dumps(dumped, indent=2))
        logger.info("Debug files saved to %s.", debug_path)

    @classmethod
    def _create_init_file(cls) -> None:
        """Create ``__init__.py`` in the model directory if it doesn't exist."""
        model_path = cls._get_model_path()
        init_path = model_path.parent / "__init__.py"
        if not init_path.exists():
            init_path.write_text(f'"""Models for {cls._get_model_name()}."""')

    # endregion Private methods
