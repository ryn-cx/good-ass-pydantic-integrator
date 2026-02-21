"""Test GAPIClient."""

import json
import tempfile
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, override

import pytest
from pydantic import BaseModel

from good_ass_pydantic_integrator import GAPIClient
from good_ass_pydantic_integrator.gapi import GAPI
from tests.constants import TEST_DATA

if TYPE_CHECKING:
    from good_ass_pydantic_integrator.constants import INPUT_TYPE


def create_initial_model(name: str, initial_data: INPUT_TYPE) -> None:
    """Create an initial Pydantic model and JSON schema."""
    model_path = Path(__file__).parent / "test_data" / f"{name}.py"
    schema_path = model_path.with_suffix(".json")

    gapi = GAPI(name)
    gapi.add_object_from_dict(initial_data)
    gapi.write_json_schema_to_file(schema_path)
    gapi.write_pydantic_model_to_file(model_path)


@pytest.mark.parametrize(
    ("initial_data", "update_data", "expected_in_model"),
    [
        # Test adding an additional field to a model.
        (
            {"string": "string"},
            {"integer": 123},
            ["string: str | None = None", "integer: int | None = None"],
        ),
        # Test modifying a list type on a model.
        ({"items": [123]}, {"items": ["string"]}, ["items: list[int | str]"]),
        # Test adding a typed list after an empty list.
        ({"items": []}, {"items": ["a"]}, ["items: list[str]"]),
        # Test modifying an existing field on a model.
        ({"mixed": "string"}, {"mixed": 123}, ["mixed: int | str"]),
        # Test adding an initial subfield on a blank model.
        (None, {"submodel": {"string": "string"}}, ["string: str"]),
        # Test adding an additional subfield on a model.
        (
            {"submodel": {"string": "string"}},
            {"submodel": {"integer": "int"}},
            ["string: str | None = None", "integer: str | None = None"],
        ),
        # Test modifying an existing subfield on a model.
        (
            {"submodel": {"mixed": "string"}},
            {"submodel": {"mixed": "int"}},
            ["mixed: str"],
        ),
        # This will clear out the final value so the final file is consistent for git.
        ({}, {}, []),
    ],
)
def test_gapi(
    initial_data: INPUT_TYPE,
    update_data: INPUT_TYPE,
    expected_in_model: list[str],
) -> None:
    """Test GAPIClient.parse."""
    # PLC0415 I001 - This import needs to be here so it imports after the initial file
    # is generated.
    from tests.test_data.simple_gapi_model import SimpleGapiModel  # noqa: PLC0415

    class TestGapiClient(GAPIClient[SimpleGapiModel]):
        """Concrete implementation of GAPIClient for testing."""

        @cached_property
        def json_files_folder(self) -> Path:
            self._json_files_temp_dir = tempfile.TemporaryDirectory()
            return Path(self._json_files_temp_dir.name)

        @cached_property
        @override
        def _response_model(self) -> type[SimpleGapiModel]:
            return SimpleGapiModel

    client = TestGapiClient()
    client.write_blank_model()
    if initial_data:
        client.parse(initial_data)
    client.parse(update_data)

    model_path = Path(__file__).parent / "test_data" / "simple_gapi_model.py"
    model_text = model_path.read_text()
    stripped_lines = [line.strip() for line in model_text.splitlines()]
    assert "any" not in model_text, model_text
    for expected_line in expected_in_model:
        assert expected_line in stripped_lines, model_text


def test_write_blank_model() -> None:
    """Test GAPIClient.write_blank_model."""
    name = "simple_gapi_model"
    create_initial_model(name, {"string": "string"})
    from tests.test_data.simple_gapi_model import SimpleGapiModel  # noqa: PLC0415

    class TestGapiClient(GAPIClient[SimpleGapiModel]):
        """Concrete implementation of GAPIClient for testing."""

        @cached_property
        @override
        def _response_model(self) -> type[SimpleGapiModel]:
            return SimpleGapiModel

    client = TestGapiClient()
    client.write_blank_model()

    model_path = Path(__file__).parent / "test_data" / f"{name}.py"
    schema_path = model_path.with_suffix(".json")
    expected_output = """# ruff: noqa: D100, D101
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SimpleGapiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
"""
    assert model_path.read_text() == expected_output
    assert not schema_path.exists()


def test_remove_redundant_files() -> None:
    """Test GAPIClient.remove_redundant_json_files."""
    name = "simple_gapi_model"
    create_initial_model(name, {"string": "string"})
    from tests.test_data.simple_gapi_model import SimpleGapiModel  # noqa: PLC0415

    class TestGapiClient(GAPIClient[SimpleGapiModel]):
        """Concrete implementation of GAPIClient for testing."""

        @cached_property
        def json_files_folder(self) -> Path:
            self._json_files_temp_dir = tempfile.TemporaryDirectory()
            return Path(self._json_files_temp_dir.name)

        @cached_property
        @override
        def _response_model(self) -> type[SimpleGapiModel]:
            return SimpleGapiModel

    client = TestGapiClient()
    number_of_files = 3
    for i in range(number_of_files):
        file_path = client.json_files_folder / f"{i}.json"
        file_path.write_text(json.dumps(TEST_DATA))

    client.remove_redundant_json_files()

    remaining_files = list(client.json_files_folder.glob("*.json"))
    assert len(remaining_files) == 1


class _TestModel(BaseModel):
    string: str
    integer: int


class TestDumpResponse:
    """Test GAPIClient.dump_response."""

    def test_dump_response(self) -> None:
        """Test dumping a single model instance."""
        model = _TestModel(string="string", integer=123)
        result = GAPIClient.dump_response(model)
        assert result == {"string": "string", "integer": 123}

    def test_dump_response_list(self) -> None:
        """Test dumping a list of model instances."""
        models = [
            _TestModel(string="string1", integer=1),
            _TestModel(string="string2", integer=2),
        ]
        result = GAPIClient.dump_response(models)
        assert result == [
            {"string": "string1", "integer": 1},
            {"string": "string2", "integer": 2},
        ]
