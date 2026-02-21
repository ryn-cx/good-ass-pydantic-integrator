"""Abstract base client for auto-generating and validating Pydantic models."""

import importlib
import inspect
import json
import re
import sys
import uuid
from abc import ABC, abstractmethod
from functools import cached_property
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, overload

from pydantic import BaseModel, ValidationError

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


class GAPIClient[T: BaseModel](ABC):
    """Base class for API endpoints to auto-generate Pydantic models from responses."""

    logger = getLogger(__name__)

    _BLANK_MODEL_TEMPLATE = """# ruff: noqa: D100, D101
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class {class_name}(BaseModel):
    model_config = ConfigDict(extra="forbid")
"""

    # region Abstract properties

    @cached_property
    @abstractmethod
    def _response_model(self) -> type[T]:
        """Return the Pydantic model class for this client."""

    # endregion Abstract properties

    # region Customizations

    @cached_property
    def _replacement_fields(self) -> list[ReplacementField]:
        """Return replacement fields to apply into generated models."""
        return []

    @cached_property
    def _replacement_types(self) -> list[ReplacementType]:
        """Return replacement types to apply into generated models."""
        return []

    @cached_property
    def _custom_serializers(self) -> list[CustomSerializer]:
        """Return custom serializers to apply into generated models."""
        return []

    @cached_property
    def _additional_imports(self) -> list[str]:
        """Return additional import lines to apply into generated models."""
        return []

    # endregion Customizations

    # region Computed properties

    @cached_property
    def _customizer(self) -> GAPICustomizer:
        """Return a customizer from the configured fields, serializers, and imports."""
        customizer = GAPICustomizer()
        customizer.replacement_fields = self._replacement_fields
        customizer.replacement_types = self._replacement_types
        customizer.custom_serializers = self._custom_serializers
        customizer.additional_imports = self._additional_imports
        return customizer

    @cached_property
    def _response_model_name(self) -> str:
        """Return the name of the response model class."""
        return self._response_model.__name__

    @cached_property
    def _response_model_folder_name(self) -> str:
        """Return the response model class name to snake_case for the folder name."""
        string = self._response_model_name
        string = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", string)
        string = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", string)
        return string.lower().removesuffix("_model")

    @cached_property
    def _response_models_path(self) -> Path:
        """Return the path to response models file."""
        return Path(inspect.getfile(self._response_model))

    @cached_property
    def _schema_path(self) -> Path:
        """Return the path to the JSON schema file for the response model."""
        return self._response_models_path.with_suffix(".json")

    @cached_property
    def _root_files_path(self) -> Path:
        """Return the path that contains the folders that contain JSON files.

        This is the root file path for all models, this should not be model specific.
        """
        return self._response_models_path.parent / "_files"

    @cached_property
    def json_files_folder(self) -> Path:
        """Return the folder that contains all saved JSON files for the model."""
        return self._root_files_path / self._response_model_folder_name

    def json_files(self) -> list[Path]:
        """Return all saved JSON files for the model."""
        return list(self.json_files_folder.glob("*.json"))

    # endregion Computed properties

    # region Static methods

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

    # endregion Static methods

    # region Public methods

    def parse(self, data: INPUT_TYPE, *, update_models: bool = True) -> T:
        """Parses data into a model.

        Args:
            data: The data to parse.
            update_models: Whether to update the models if parsing fails.

        Returns:
            A model instance containing the parsed data.
        """
        if update_models:
            return self._parse_and_validate(data)

        return self._response_model.model_validate(data)

    def rebuild_models(self) -> None:
        """Rebuild the schema and model from all saved files."""
        client = GAPI(self._response_model_name, customizer=self._customizer)
        if any(self.json_files()):
            client.add_objects_from_folder(self.json_files_folder)
            client.write_json_schema_to_file(self._schema_path)
            client.write_pydantic_model_to_file(self._response_models_path)
            self._create_init_file()
        else:
            self.write_blank_model()

        self._response_model = self._reload_models()

    def write_blank_model(self) -> None:
        """Replace the existing model and schema with blank template files.

        The schema file will be deleted, and the model will be overwritten with a
        template that contains no fields.
        """
        content = self._BLANK_MODEL_TEMPLATE.format(
            class_name=self._response_model_name,
        )
        self._response_models_path.write_text(content)
        if self._schema_path.exists():
            self._schema_path.unlink()
        self._response_model = self._reload_models()

    def remove_redundant_json_files(self) -> None:
        """Remove JSON files that are redundant for schema generation."""
        input_files = list(self.json_files())

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
                self.logger.info("Deleting Redundant File: %s", input_files[i].name)
                input_files[i].unlink()
                input_files.pop(i)
            else:
                i += 1

    # endregion Public methods

    # region Private methods

    def _parse_and_validate(self, data: INPUT_TYPE) -> T:
        """Validate data against the response model, auto-updating on failure.

        Args:
            data: The raw API response data.

        Returns:
            The validated model instance.
        """
        try:
            parsed = self._response_model.model_validate(data)
        # If validation fails try automatically rebuilding and reloading the models
        # using the new data and see if validation will succeed with the updated models.
        except ValidationError:
            self.logger.info("Updating model %s.", self._response_model_name)

            new_file = self._save_new_json_file(data)
            self._update_models(new_file)

            # If validation fails a second time this will raise an error that must be
            # handled manually.
            parsed = self._response_model.model_validate(data)

        # If the dumped response does not match the original input then there is an
        # issue with the parsing or dumping logic that needs to be manually fixed.
        dumped = self.dump_response(parsed)
        if dumped != data:
            self._save_debug_files(data, dumped)
            msg = "Parsed response does not match original response."
            raise ValueError(msg)

        return parsed

    def _update_models(self, new_file_path: Path) -> None:
        """Update the schema and model with new data.

        Args:
            new_file_path: Path to a JSON file containing the new data.
        """
        gapi = GAPI(self._response_model_name, customizer=self._customizer)
        if self._schema_path.exists():
            gapi.add_schema_from_file(self._schema_path)
        gapi.add_object_from_file(new_file_path)
        gapi.write_json_schema_to_file(self._schema_path)
        gapi.write_pydantic_model_to_file(self._response_models_path)
        self._response_model = self._reload_models()

    def _reload_models(self) -> type[T]:
        """Reload a model by reimporting it.

        Returns:
            The reloaded model class.
        """
        module = sys.modules[self._response_model.__module__]

        if hasattr(module, "__cached__") and module.__cached__:
            cached_path = Path(module.__cached__)
            if cached_path.exists():
                cached_path.unlink()

        reloaded_module = importlib.reload(module)
        return getattr(reloaded_module, self._response_model_name)

    def _save_new_json_file(self, data: INPUT_TYPE) -> Path:
        """Save response data as a JSON file for future model rebuilds."""
        json_path = self.json_files_folder / f"{uuid.uuid4()}.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(data, indent=2))
        return json_path

    def _save_debug_files(self, data: INPUT_TYPE, dumped: INPUT_TYPE) -> None:
        """Save original and parsed data for debugging round-trip mismatches."""
        self._save_new_json_file(data)
        debug_path = self._root_files_path / "_temp" / self._response_model_folder_name
        debug_path.mkdir(parents=True, exist_ok=True)
        (debug_path / "original.json").write_text(json.dumps(data, indent=2))
        (debug_path / "parsed.json").write_text(json.dumps(dumped, indent=2))

    def _create_init_file(self) -> None:
        """Create ``__init__.py`` in the models directory if it doesn't exist."""
        init_path = self._response_models_path.parent / "__init__.py"
        if not init_path.exists():
            init_path.write_text(f'"""Models for {self._response_model_name}."""')

    # endregion Private methods
