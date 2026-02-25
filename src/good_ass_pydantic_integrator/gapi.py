"""GAPI core schema generation and Pydantic model code generation."""

from __future__ import annotations

import json
import shutil
import subprocess
from functools import cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING

import datamodel_code_generator
from datamodel_code_generator.format import Formatter
from degenson import SchemaBuilder

from good_ass_pydantic_integrator.convert import convert_input_data
from good_ass_pydantic_integrator.customizer import GAPICustomizer

if TYPE_CHECKING:
    from good_ass_pydantic_integrator.constants import INPUT_TYPE


def _confirm_uv_exists() -> None:
    """Raise FileNotFoundError if uv is not installed."""
    if not shutil.which("uv"):
        msg = "uv was not found"
        raise FileNotFoundError(msg)


@cache
def build_ruff_noqa_line() -> str:
    """Build a ``# ruff: noqa:`` line for all ruff rule codes.

    Returns:
        A noqa comment line containing all ruff rule codes.
    """
    return "# ruff: noqa: D100, D101, D102\n"


def format_with_ruff(content: str) -> str:
    """Format Python code by running ``uv run ruff``.

    Args:
        content: The Python source code to format.

    Returns:
        The formatted Python source code.
    """
    _confirm_uv_exists()

    check_result = subprocess.run(
        [  # noqa: S607
            "uv",
            "run",
            "ruff",
            "check",
            "--fix",
            "--stdin-filename",
            "temp.py",
            "-",
            "--unsafe-fixes",
        ],
        input=content,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    if not check_result.stdout:
        msg = f"Ruff formatting failed with error: {check_result.stderr}"
        raise RuntimeError(msg)

    format_result = subprocess.run(
        ["uv", "run", "ruff", "format", "--stdin-filename", "temp.py", "-"],  # noqa: S607
        input=check_result.stdout,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    if not format_result.stdout:
        msg = f"Ruff formatting failed with error: {format_result.stderr}"
        raise RuntimeError(msg)

    return format_result.stdout


class GAPI:
    """Generate JSON schemas and Pydantic models from JSON data."""

    def __init__(
        self,
        class_name: str | None = None,
        *,
        builder: SchemaBuilder | None = None,
        customizer: GAPICustomizer | None = None,
        convert: bool = True,
    ) -> None:
        """Initialize GAPI.

        Args:
            class_name: Name for the root generated model class.
            builder: Pre-configured SchemaBuilder instance to build upon.
            customizer: Customizer for post-generation field/serializer/import changes.
            convert: Auto-detect and convert date/datetime/timedelta strings.
        """
        self.convert = convert
        self.builder = builder or SchemaBuilder()
        self._customizer = customizer or GAPICustomizer()

        self.class_name = class_name

        self.cached_json_schema: str | None = None
        self.cached_pydantic_model: str | None = None

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
        self.cached_pydantic_model = None

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
        self.cached_pydantic_model = None

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

    def get_pydantic_model_content(self) -> str:
        """Generate the Pydantic model code as a string, caching the result.

        Returns:
            The generated Pydantic model source code.
        """
        if self.cached_pydantic_model is not None:
            return self.cached_pydantic_model

        with NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete_on_close=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.close()

            datamodel_code_generator.generate(
                # reportUnknownMemberType - Error is from the library.
                input_=self.get_json_schema_content(),  # type: ignore[reportUnknownMemberType]
                output=temp_path,
                class_name=self.class_name,
                input_file_type=datamodel_code_generator.InputFileType.JsonSchema,
                output_model_type=datamodel_code_generator.DataModelType.PydanticV2BaseModel,
                snake_case_field=True,
                disable_timestamp=True,
                extra_fields="forbid",
                target_python_version=datamodel_code_generator.PythonVersion.PY_313,
                output_datetime_class=datamodel_code_generator.DatetimeClassType.Awaredatetime,
                formatters=[Formatter.RUFF_FORMAT, Formatter.RUFF_CHECK],
            )

            content = temp_path.read_text()
            temp_path.unlink()

        content = self._customizer.apply_customizations(content)
        content = format_with_ruff(content)
        content = build_ruff_noqa_line() + content
        self.cached_pydantic_model = format_with_ruff(content)
        return self.cached_pydantic_model

    def write_pydantic_model_to_file(self, output_path: Path) -> None:
        """Generate and write the Pydantic model to a file.

        Args:
            output_path: Path to write the Pydantic model file to.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.get_pydantic_model_content())
