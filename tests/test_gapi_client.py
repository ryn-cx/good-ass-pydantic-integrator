# TODO: Validate
"""Test GAPIClient."""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError

from good_ass_pydantic_integrator import GAPIBaseModel, GAPIClient, ParseLevel
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


class TestParseLevel:
    """Test the recovery stages GAPIClient.parse runs through."""

    @staticmethod
    def _client(setup: INPUT_TYPE | None = None) -> type[GAPIClient[Any]]:
        """Return a client whose model was generated from `setup`.

        Defaults to a model that accepts `{"string": ...}`.
        """
        from tests.test_data.simple_gapi_model import SimpleGapiModel  # noqa: PLC0415

        temp_dir = tempfile.TemporaryDirectory()

        class TestGapiClient(GAPIClient[SimpleGapiModel]):
            """Concrete implementation of GAPIClient for testing."""

            _response_model = SimpleGapiModel
            regenerate = True
            """Turned off after setup so the stages that follow regeneration are
            reachable with data the generator would otherwise absorb."""

            @classmethod
            def json_files_folder(cls) -> Path:
                return Path(temp_dir.name)

            @classmethod
            def _update_model(cls, new_file_path: Path) -> None:
                if cls.regenerate:
                    super()._update_model(new_file_path)

        TestGapiClient.write_blank_model()
        TestGapiClient.parse(setup if setup is not None else {"string": "string"})
        TestGapiClient.regenerate = False
        return TestGapiClient

    def test_strict_saves_without_updating(self) -> None:
        """STRICT saves the failing data as a sample, then raises."""
        client = self._client()
        saved = client.json_files()
        model = client._response_model  # noqa: SLF001 - Checking the model is untouched.
        with pytest.raises(ValidationError):
            client.parse({"unknown": "value"}, level=ParseLevel.STRICT)
        assert len(client.json_files()) == len(saved) + 1
        assert client._response_model is model  # noqa: SLF001 - As above.
        client.write_blank_model()

    def test_update_regenerates(self) -> None:
        """UPDATE saves the data as a new sample and rebuilds the model from it."""
        from tests.test_data.simple_gapi_model import SimpleGapiModel  # noqa: PLC0415

        temp_dir = tempfile.TemporaryDirectory()

        class TestGapiClient(GAPIClient[SimpleGapiModel]):
            """Concrete implementation of GAPIClient for testing."""

            _response_model = SimpleGapiModel

            @classmethod
            def json_files_folder(cls) -> Path:
                return Path(temp_dir.name)

        TestGapiClient.write_blank_model()
        parsed = TestGapiClient.parse({"string": "string"})

        assert len(TestGapiClient.json_files()) == 1
        assert TestGapiClient.original_input(parsed) == {"string": "string"}
        TestGapiClient.write_blank_model()

    def test_allow_extra_ignores_unknown_fields(self) -> None:
        """ALLOW_EXTRA parses data that only fails because of extra fields."""
        client = self._client()
        data = {"string": "string", "unknown": "value"}

        with pytest.raises(ValidationError):
            client.parse(data, level=ParseLevel.UPDATE)
        parsed = client.parse(data, level=ParseLevel.ALLOW_EXTRA)

        assert parsed.string == "string"
        assert not hasattr(parsed, "unknown")
        client.write_blank_model()

    def test_extra_forbid_is_restored(self) -> None:
        """The `extra="forbid"` override only lasts for the relaxed attempt."""
        client = self._client()
        client.parse(
            {"string": "string", "unknown": "value"},
            level=ParseLevel.ALLOW_EXTRA,
        )

        with pytest.raises(ValidationError):
            client.parse(
                {"string": "string", "unknown": "value"},
                level=ParseLevel.STRICT,
            )
        client.write_blank_model()

    def test_allow_extra_still_raises(self) -> None:
        """ALLOW_EXTRA raises when extra fields are not what makes the data fail."""
        client = self._client()
        with pytest.raises(ValidationError):
            client.parse({"string": [1, 2]}, level=ParseLevel.ALLOW_EXTRA)
        client.write_blank_model()

    def test_allow_missing_parses_partial_data(self) -> None:
        """ALLOW_MISSING fills in missing fields, nested ones included, with None."""
        client = self._client(
            {
                "top": "top",
                "sub": {"name": "name", "when": "2000-01-01T00:00:00Z"},
                "items": [{"id": 1}],
            },
        )
        # Every field above is required, and this drops one at each level.
        data = {"sub": {"when": "2000-01-01T00:00:00Z"}, "items": [{}]}

        with pytest.raises(ValidationError):
            client.parse(data, level=ParseLevel.ALLOW_EXTRA)
        parsed = client.parse(data, level=ParseLevel.ALLOW_MISSING)

        assert parsed.top is None
        assert parsed.sub.name is None
        assert parsed.items[0].id is None
        # The value that is present is still validated and coerced as usual.
        assert parsed.sub.when == datetime(2000, 1, 1, tzinfo=UTC)
        client.write_blank_model()

    def test_allow_missing_returns_the_response_model(self) -> None:
        """The relaxed model is a subclass, so the return type is not a lie."""
        client = self._client()
        parsed = client.parse({}, level=ParseLevel.ALLOW_MISSING)

        # Imported after the client regenerates the model, since regenerating
        # reloads the module and replaces the class object.
        from tests.test_data.simple_gapi_model import SimpleGapiModel  # noqa: PLC0415

        assert isinstance(parsed, SimpleGapiModel)
        assert client.original_input(parsed) == {}
        client.write_blank_model()

    def test_allow_missing_saves_the_data(self) -> None:
        """Data that only parses when relaxed is still saved for later analysis."""
        client = self._client()
        saved = client.json_files()

        client.parse({}, level=ParseLevel.ALLOW_MISSING)

        assert len(client.json_files()) == len(saved) + 1
        client.write_blank_model()

    def test_allow_missing_leaves_the_response_model_strict(self) -> None:
        """Relaxing happens on a throwaway subclass, not the response model."""
        client = self._client()
        client.parse({}, level=ParseLevel.ALLOW_MISSING)

        with pytest.raises(ValidationError):
            client.parse({}, level=ParseLevel.STRICT)
        client.write_blank_model()


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
        # Pydantic normalizes the datetime, dropping the redundant ".000"
        # milliseconds, so model_dump re-serializes to a "Z" without them. Only
        # original_input recovers the exact raw value the model was built from.
        data = {"created_at": "2000-01-01T00:00:00.000Z"}
        parsed = TestGapiClient.parse(data)

        assert TestGapiClient.model_dump(parsed) == {
            "created_at": "2000-01-01T00:00:00Z",
        }
        assert TestGapiClient.original_input(parsed) is data
