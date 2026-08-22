# TODO: Validate
"""GAPI core schema generation and Pydantic model code generation."""

import ast
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING

import datamodel_code_generator
from datamodel_code_generator.format import Formatter
from degenson import SchemaBuilder

from good_ass_pydantic_integrator.constants import MODELS_TEMPLATE
from good_ass_pydantic_integrator.convert import convert_input_data
from good_ass_pydantic_integrator.customizer import GAPICustomizer

if TYPE_CHECKING:
    from good_ass_pydantic_integrator.constants import INPUT_TYPE, JSON_VALUE


class GAPI:
    """Generate JSON schemas and Pydantic models from JSON data."""

    # TODO: Validate
    def __init__(
        self,
        class_name: str | None = None,
        *,
        builder: SchemaBuilder | None = None,
        customizer: GAPICustomizer | None = None,
        convert: bool = True,
        base_class: str = "",
    ) -> None:
        """Initialize GAPI.

        Args:
            class_name: Name for the root generated model class.
            builder: Pre-configured SchemaBuilder instance to build upon.
            customizer: Customizer for post-generation field/serializer/import changes.
            convert: Auto-detect and convert date/datetime/timedelta strings.
            base_class: Dotted path to the base class generated models inherit
                from. Defaults to `pydantic.BaseModel`.
        """
        self.convert = convert
        self.builder = builder or SchemaBuilder()
        self._customizer = customizer or GAPICustomizer()

        self.class_name = class_name
        self.base_class = base_class

        self.cached_json_schema: str | None = None
        self.cached_required_models: str | None = None
        self.cached_optional_models: str | None = None

    def add_schema_from_file(self, schema_path: Path) -> None:
        """Load a JSON schema from a file path into the SchemaBuilder.

        Args:
            schema_path: Path to the JSON schema file.
        """
        self.add_schema_from_string(schema_path.read_text())

    def add_schema_from_string(self, schema_string: str) -> None:
        """Load a JSON schema string into the SchemaBuilder.

        Args:
            schema_string: The JSON schema as a string.
        """
        self.add_schema_from_dict(json.loads(schema_string))

    def add_schema_from_dict(self, schema_dict: dict[str, INPUT_TYPE]) -> None:
        """Load a JSON schema dict into the SchemaBuilder.

        Args:
            schema_dict: The JSON schema as a dictionary.
        """
        self.cached_json_schema = None
        self.cached_required_models = None
        self.cached_optional_models = None

        self.builder.add_schema(schema_dict)

    def add_objects_from_folder(
        self,
        folder_path: Path,
    ) -> None:
        """Load multiple JSON objects from files in a folder into the SchemaBuilder.

        Args:
            folder_path: Path to the folder containing JSON files.
        """
        for json_file in sorted(folder_path.glob("*.json")):
            self.add_object_from_file(json_file)

    # TODO: Validate
    @classmethod
    def redundant_json_files(
        cls,
        folder_path: Path,
        *,
        convert: bool = True,
    ) -> list[Path]:
        """Return the JSON files in a folder that the schema does not need.

        A file is redundant when the schema built from every other file is the
        same as the schema built from all of them. The newest files are checked
        first, so of two files that say the same thing the older one is kept.

        Args:
            folder_path: Path to the folder containing JSON files.
            convert: Auto-detect and convert date/datetime/timedelta strings.

        Returns:
            The redundant files, in the order they were found.
        """
        newest_first = sorted(folder_path.glob("*.json"), reverse=True)
        redundant: list[Path] = []

        def schema_without(skipped: Path | None) -> SchemaBuilder:
            gapi = cls(convert=convert)
            for json_file in newest_first:
                if json_file != skipped and json_file not in redundant:
                    gapi.add_object_from_file(json_file)
            return gapi.builder

        complete_schema = schema_without(None)
        for json_file in newest_first:
            if schema_without(json_file) == complete_schema:
                # PERF401 - Not a comprehension: `schema_without` reads this
                # list, so two files that say the same thing do not both end up
                # in it.
                redundant.append(json_file)  # noqa: PERF401
        return redundant

    def add_object_from_file(self, file_path: Path) -> None:
        """Load a JSON object from a file into the SchemaBuilder.

        Args:
            file_path: Path to the JSON file.
        """
        self.add_object_from_string(file_path.read_text())

    def add_object_from_string(self, data_string: str) -> None:
        """Load a JSON object from a string into the SchemaBuilder.

        Args:
            data_string: The JSON data as a string.
        """
        data = json.loads(data_string)
        self.add_object_from_dict(data)

    def add_object_from_dict(self, data: INPUT_TYPE) -> None:
        """Load a JSON object from a dict or list into the SchemaBuilder.

        Args:
            data: The JSON data as a dict or list.
        """
        self.cached_json_schema = None
        self.cached_required_models = None
        self.cached_optional_models = None

        if self.convert:
            data = convert_input_data(data)

        # reportUnknownMemberType - Error is from the library.
        self.builder.add_object(data)  # type: ignore[reportUnknownMemberType]

    def get_json_schema_content(self) -> str:
        """Return the generated JSON schema as a string, caching the result.

        Returns:
            The JSON schema content.
        """
        if self.cached_json_schema is not None:
            return self.cached_json_schema
        # reportUnknownMemberType - Error is from the library.
        self.cached_json_schema = self.builder.to_json()  # type: ignore[reportUnknownMemberType]
        return self.cached_json_schema

    def write_json_schema_to_file(self, output_path: Path) -> None:
        """Write the generated JSON schema to a file.

        Args:
            output_path: Path to write the JSON schema file to.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.get_json_schema_content() + "\n")

    # TODO: Validate
    @classmethod
    def _relaxed_schema(cls, schema: JSON_VALUE) -> JSON_VALUE:
        """Return a copy of a JSON schema that accepts anything the original does.

        A field that has only ever been null is left untyped so it accepts a
        value if one ever turns up.
        """
        if isinstance(schema, list):
            return [cls._relaxed_schema(item) for item in schema]
        if not isinstance(schema, dict):
            return schema

        return {
            keyword: cls._relaxed_schema(value)
            for keyword, value in schema.items()
            if not (keyword == "type" and value in ("null", ["null"]))
        }

    # TODO: Validate
    def get_optional_models_content(self) -> str:
        """Generate the all-optional Pydantic model code, caching the result.

        The classes are named exactly as they are in the required model, so
        the two belong in separate files.

        Returns:
            The generated Pydantic model source code.
        """
        if self.cached_optional_models is None:
            relaxed = self._relaxed_schema(json.loads(self.get_json_schema_content()))
            self.cached_optional_models = self._generate_model(
                json.dumps(relaxed),
                extra_fields="ignore",
                force_optional=True,
            )
        return self.cached_optional_models

    # TODO: Validate
    def _model_class_names(self) -> list[str]:
        """Return the names of every class in the generated model, sorted."""
        tree = ast.parse(self.get_required_models_content())
        return sorted(node.name for node in tree.body if isinstance(node, ast.ClassDef))

    # TODO: Validate
    def get_models_content(
        self,
        required_module: str = ".required_models",
        optional_module: str = ".optional_models",
    ) -> str:
        """Generate a module that picks a model to use depending on the situation.

        A type checker reads the required model and the running program
        imports the all-optional copy, so the models are typed as the schema
        recorded them and a response that has drifted still parses.

        Args:
            required_module: Module the required model is defined in.
            optional_module: Module the all-optional model is defined in.

        Returns:
            The generated module source code.
        """
        class_names = self._model_class_names()
        return MODELS_TEMPLATE.format(
            class_name=self.class_name,
            required_module=required_module,
            optional_module=optional_module,
            names="".join(f"        {name},\n" for name in class_names),
            exports="".join(f'    "{name}",\n' for name in class_names),
        )

    # TODO: Validate
    def write_models_to_file(
        self,
        output_path: Path,
        required_module: str = ".required_models",
        optional_module: str = ".optional_models",
    ) -> None:
        """Generate and write the module that picks a model to use.

        Args:
            output_path: Path to write the module to.
            required_module: Module the required model is defined in.
            optional_module: Module the all-optional model is defined in.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            self.get_models_content(required_module, optional_module),
        )

    # TODO: Validate
    def write_optional_models_to_file(self, output_path: Path) -> None:
        """Generate and write the all-optional Pydantic model to a file.

        Args:
            output_path: Path to write the Pydantic model file to.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.get_optional_models_content())

    # TODO: Validate
    def get_required_models_content(self) -> str:
        """Generate the Pydantic model code as a string, caching the result.

        Returns:
            The generated Pydantic model source code.
        """
        if self.cached_required_models is None:
            self.cached_required_models = self._generate_model(
                self.get_json_schema_content(),
            )
        return self.cached_required_models

    # TODO: Validate
    def _generate_model(
        self,
        schema_content: str,
        *,
        extra_fields: str | None = None,
        force_optional: bool = False,
    ) -> str:
        """Generate customized Pydantic model code from a JSON schema string.

        Args:
            schema_content: The JSON schema to generate the model from.
            extra_fields: What the generated models do with unknown fields.
                Left unset the models use the Pydantic default.
            force_optional: Make every required field optional.

        Returns:
            The generated Pydantic model source code.
        """
        with NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete_on_close=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.close()

            datamodel_code_generator.generate(
                # reportUnknownMemberType - Error is from the library.
                input_=schema_content,  # type: ignore[reportUnknownMemberType]
                output=temp_path,
                class_name=self.class_name,
                input_file_type=datamodel_code_generator.InputFileType.JsonSchema,
                output_model_type=datamodel_code_generator.DataModelType.PydanticV2BaseModel,
                base_class=self.base_class,
                snake_case_field=True,
                disable_timestamp=True,
                extra_fields=extra_fields,
                force_optional_for_required_fields=force_optional,
                target_python_version=datamodel_code_generator.PythonVersion.PY_313,
                output_datetime_class=datamodel_code_generator.DatetimeClassType.Awaredatetime,
                formatters=[Formatter.RUFF_FORMAT, Formatter.RUFF_CHECK],
                disable_future_imports=True,
            )

            content = temp_path.read_text()
            temp_path.unlink()

        return self._customizer.apply_customizations(
            content,
            mark_untyped_lists=not force_optional,
            root_class_name=self.class_name,
        )

    # TODO: Validate
    def write_required_models_to_file(self, output_path: Path) -> None:
        """Generate and write the Pydantic model to a file.

        Args:
            output_path: Path to write the Pydantic model file to.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.get_required_models_content())
