# TODO: Validate
"""Test GAPIClient."""

import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from good_ass_pydantic_integrator import GAPIBaseModel, GAPIClient
from good_ass_pydantic_integrator.gapi import GAPI
from tests.constants import TEST_DATA

if TYPE_CHECKING:
    from good_ass_pydantic_integrator.constants import INPUT_TYPE


def create_initial_model(name: str, initial_data: INPUT_TYPE) -> None:
    """Create an initial Pydantic model and JSON schema."""
    model_path = Path(__file__).parent / "test_data" / f"{name}.py"
    schema_path = model_path.with_suffix(".json")

    gapi = GAPI(
        name,
        base_class=f"good_ass_pydantic_integrator.{GAPIBaseModel.__qualname__}",
    )
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

    temp_dir = tempfile.TemporaryDirectory()

    class TestGapiClient(GAPIClient[SimpleGapiModel]):
        """Concrete implementation of GAPIClient for testing."""

        _response_model = SimpleGapiModel

        @classmethod
        def json_files_folder(cls) -> Path:
            return Path(temp_dir.name)

    TestGapiClient.write_blank_model()
    if initial_data:
        TestGapiClient.parse(initial_data)
    TestGapiClient.parse(update_data)

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

        _response_model = SimpleGapiModel

    TestGapiClient.write_blank_model()

    model_path = Path(__file__).parent / "test_data" / f"{name}.py"
    schema_path = model_path.with_suffix(".json")
    expected_output = """# ruff: noqa: D100, D101
from good_ass_pydantic_integrator import GAPIBaseModel
from pydantic import ConfigDict


class SimpleGapiModel(GAPIBaseModel):
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

        _response_model = SimpleGapiModel

    json_folder = TestGapiClient.json_files_folder()
    json_folder.mkdir(parents=True, exist_ok=True)

    number_of_files = 3
    for i in range(number_of_files):
        file_path = json_folder / f"{i}.json"
        file_path.write_text(json.dumps(TEST_DATA))

    try:
        TestGapiClient.remove_redundant_json_files()

        remaining_files = list(json_folder.glob("*.json"))
        assert len(remaining_files) == 1
    finally:
        for f in json_folder.glob("*.json"):
            f.unlink()
        json_folder.rmdir()


def test_invalid_response_model_raises() -> None:
    """Test that __init_subclass__ rejects non-GAPIBaseModel _response_model."""
    match = "_response_model must be a GAPIBaseModel or RootModel subclass"
    with pytest.raises(TypeError, match=match):

        class _BadClient(GAPIClient[GAPIBaseModel]):
            _response_model = str  # type: ignore[assignment]


class _TestModel(GAPIBaseModel):
    string: str
    integer: int


class TestOriginalInput:
    """Test GAPIClient.original_input."""

    def test_original_input(self) -> None:
        """A single model returns its raw input verbatim."""
        data = {"string": "string", "integer": 123}
        model = _TestModel.model_validate(data)
        assert GAPIClient.original_input(model) is data

    def test_original_input_list(self) -> None:
        """A list of models returns each model's raw input."""
        data1 = {"string": "string1", "integer": 1}
        data2 = {"string": "string2", "integer": 2}
        models = [
            _TestModel.model_validate(data1),
            _TestModel.model_validate(data2),
        ]
        assert GAPIClient.original_input(models) == [data1, data2]

    def test_original_input_unvalidated_raises(self) -> None:
        """A model built without validation has no raw input and cannot be dumped."""
        model = _TestModel.model_construct(string="string", integer=123)
        with pytest.raises(ValueError, match="no raw input"):
            GAPIClient.original_input(model)

    def test_original_input_returns_raw_input(self) -> None:
        """A parsed model returns the exact raw input, not model_dump output."""
        from tests.test_data.simple_gapi_model import SimpleGapiModel  # noqa: PLC0415

        temp_dir = tempfile.TemporaryDirectory()

        class TestGapiClient(GAPIClient[SimpleGapiModel]):
            """Concrete implementation of GAPIClient for testing."""

            _response_model = SimpleGapiModel

            @classmethod
            def json_files_folder(cls) -> Path:
                return Path(temp_dir.name)

        TestGapiClient.write_blank_model()
        # A datetime string that model_dump would re-serialize as "+00:00" instead
        # of the original "Z", proving the raw input is returned verbatim.
        data = {"created_at": "2000-01-01T00:00:00Z"}
        parsed = TestGapiClient.parse(data)

        assert TestGapiClient.original_input(parsed) is data

    def test_original_input_root_list_model(self) -> None:
        """A root model built from a top-level list returns the input list."""
        from tests.test_data.simple_gapi_model import SimpleGapiModel  # noqa: PLC0415

        temp_dir = tempfile.TemporaryDirectory()

        class TestGapiClient(GAPIClient[SimpleGapiModel]):
            """Concrete implementation of GAPIClient for testing."""

            _response_model = SimpleGapiModel

            @classmethod
            def json_files_folder(cls) -> Path:
                return Path(temp_dir.name)

        TestGapiClient.write_blank_model()
        # A top-level JSON list makes the generated root model a RootModel, which
        # records no raw input itself; original_input rebuilds it from the items.
        data: list[dict[str, int]] = [{"id": 1}, {"id": 2}]
        parsed = TestGapiClient.parse(data)

        assert TestGapiClient.original_input(parsed) == data


class TestModelDump:
    """Test GAPIClient.model_dump."""

    def test_model_dump(self) -> None:
        """A single model returns its Pydantic-serialized fields."""
        data = {"string": "string", "integer": 123}
        model = _TestModel.model_validate(data)
        assert GAPIClient.model_dump(model) == data

    def test_model_dump_list(self) -> None:
        """A list of models returns each model's serialized fields."""
        data1 = {"string": "string1", "integer": 1}
        data2 = {"string": "string2", "integer": 2}
        models = [
            _TestModel.model_validate(data1),
            _TestModel.model_validate(data2),
        ]
        assert GAPIClient.model_dump(models) == [data1, data2]

    def test_model_dump_reserializes_not_raw_input(self) -> None:
        """model_dump reflects the model's serialized value, not the raw input."""
        from tests.test_data.simple_gapi_model import SimpleGapiModel  # noqa: PLC0415

        temp_dir = tempfile.TemporaryDirectory()

        class TestGapiClient(GAPIClient[SimpleGapiModel]):
            """Concrete implementation of GAPIClient for testing."""

            _response_model = SimpleGapiModel

            @classmethod
            def json_files_folder(cls) -> Path:
                return Path(temp_dir.name)

        TestGapiClient.write_blank_model()
        # The raw input uses a "Z" suffix; Pydantic re-serializes it as "+00:00",
        # so model_dump differs from original_input for the same model.
        data = {"created_at": "2000-01-01T00:00:00Z"}
        parsed = TestGapiClient.parse(data)

        assert TestGapiClient.model_dump(parsed) == {
            "created_at": "2000-01-01T00:00:00Z",
        }
        assert TestGapiClient.original_input(parsed) is data
