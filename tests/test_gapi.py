# TODO: Validate
"""Test GAPI."""

import json
from typing import TYPE_CHECKING, Any

import pytest

from good_ass_pydantic_integrator.customizer import GAPICustomizer
from good_ass_pydantic_integrator.gapi import GAPI
from tests.constants import MODEL_PATH, SCHEMA_PATH, TEST_DATA, TEST_DATA_PATH

if TYPE_CHECKING:
    from pathlib import Path

    from good_ass_pydantic_integrator.constants import INPUT_TYPE


class TestAddSchema:
    """Test adding schema from various sources."""

    @pytest.mark.parametrize(
        ("method_name", "input_arg"),
        [
            ("add_schema_from_file", SCHEMA_PATH),
            ("add_schema_from_dict", json.loads(SCHEMA_PATH.read_text())),
            ("add_schema_from_string", SCHEMA_PATH.read_text()),
        ],
        ids=["file", "dict", "string"],
    )
    def test_add_schema(
        self,
        method_name: str,
        input_arg: Path | INPUT_TYPE | str,
    ) -> None:
        """Test adding schema from file, dict, or string."""
        gapi = GAPI()
        getattr(gapi, method_name)(input_arg)
        assert gapi.get_required_models_content() == MODEL_PATH.read_text()


class TestAddObject:
    """Test adding objects from various sources."""

    @pytest.mark.parametrize(
        ("method_name", "input_arg"),
        [
            ("add_object_from_file", TEST_DATA_PATH),
            ("add_object_from_dict", TEST_DATA),
            ("add_object_from_string", json.dumps(TEST_DATA)),
        ],
        ids=["file", "dict", "string"],
    )
    def test_add_object(
        self,
        method_name: str,
        input_arg: Path | INPUT_TYPE | str,
    ) -> None:
        """Test adding object from file, dict, or string."""
        gapi = GAPI()
        getattr(gapi, method_name)(input_arg)
        assert gapi.get_required_models_content() == MODEL_PATH.read_text()


class TestReplaceField:
    """Test add_replacement_field."""

    def test_add_replacement_field(self) -> None:
        """Test applying a replacement field."""
        customizer = GAPICustomizer()
        customizer.add_replacement_field(
            class_name="Model",
            field_name="integer_that_is_stored_as_a_string",
            new_field="""integer_that_is_stored_as_a_string: int""",
        )
        gapi = GAPI(customizer=customizer)
        gapi.add_object_from_dict({"integer_that_is_stored_as_a_string": "1"})
        lines = gapi.get_required_models_content().splitlines()
        assert "    integer_that_is_stored_as_a_string: int" in lines

    def test_add_replacement_field_without_field_name_prefix(self) -> None:
        """Test passing a new_field that omits the `field_name:` prefix."""
        customizer = GAPICustomizer()
        customizer.add_replacement_field(
            class_name="Model",
            field_name="integer_that_is_stored_as_a_string",
            new_field="int",
        )
        gapi = GAPI(customizer=customizer)
        gapi.add_object_from_dict({"integer_that_is_stored_as_a_string": "1"})
        lines = gapi.get_required_models_content().splitlines()
        assert "    integer_that_is_stored_as_a_string: int" in lines

    def test_add_replacement_field_over_multiple_lines(self) -> None:
        """Test applying a replacement field that spans multiple lines."""
        customizer = GAPICustomizer()
        customizer.add_replacement_field(
            class_name="Model",
            field_name="integer_that_is_stored_as_a_string",
            new_field="""integer_that_is_stored_as_a_string: int = Field(
        ...,
        alias="IntegerThatIsStoredAsAString",
    )""",
        )
        gapi = GAPI(customizer=customizer)
        gapi.add_object_from_dict({"IntegerThatIsStoredAsAString": "1"})
        lines = gapi.get_required_models_content().splitlines()
        assert (
            "    integer_that_is_stored_as_a_string: int ="
            " Field(..., alias='IntegerThatIsStoredAsAString')" in lines
        )


class TestReplaceType:
    """Test add_replacement_type."""

    def test_add_replacement_type(self) -> None:
        """Test replacing just the type annotation of a field."""
        customizer = GAPICustomizer()
        customizer.add_replacement_type(
            class_name="Model",
            field_name="integer_that_is_stored_as_a_string",
            new_type="int",
        )
        gapi = GAPI(customizer=customizer)
        gapi.add_object_from_dict({"integer_that_is_stored_as_a_string": "1"})
        lines = gapi.get_required_models_content().splitlines()
        assert "    integer_that_is_stored_as_a_string: int" in lines

    def test_add_replacement_type_preserves_alias(self) -> None:
        """Test that replacing a type preserves the field alias."""
        customizer = GAPICustomizer()
        customizer.add_replacement_type(
            class_name="Model",
            field_name="integer_that_is_stored_as_a_string",
            new_type="int",
        )
        gapi = GAPI(customizer=customizer)
        gapi.add_object_from_dict({"IntegerThatIsStoredAsAString": "1"})
        lines = gapi.get_required_models_content().splitlines()
        assert (
            "    integer_that_is_stored_as_a_string: int ="
            " Field(..., alias='IntegerThatIsStoredAsAString')" in lines
        )


class TestAddSerializers:
    """Test add_serializer."""

    def test_add_serializer(self) -> None:
        """Test adding a custom serializer."""
        customizer = GAPICustomizer()
        customizer.add_custom_serializer(
            field_name="string",
            serializer_code="return output",
            output_type="str",
        )
        gapi = GAPI(customizer=customizer)
        gapi.add_object_from_dict({"string": "string"})
        content = gapi.get_required_models_content()
        assert (
            """    @field_serializer('string')
    def serialize_string(self, value: str) -> str:
        return output"""
            in content
        )

    def test_add_multiple_serializers(self) -> None:
        """Test adding multiple custom serializers."""
        customizer = GAPICustomizer()
        customizer.add_custom_serializer(
            field_name="string",
            serializer_code="return output",
            output_type="str",
        )
        customizer.add_custom_serializer(
            field_name="string2",
            serializer_code="return output",
            output_type="str",
        )
        gapi = GAPI(customizer=customizer)
        gapi.add_object_from_dict({"string": "string", "string2": "string2"})
        content = gapi.get_required_models_content()
        assert (
            """    @field_serializer('string')
    def serialize_string(self, value: str) -> str:
        return output"""
            in content
        )
        assert (
            """    @field_serializer('string2')
    def serialize_string2(self, value: str) -> str:
        return output"""
            in content
        )

    @pytest.mark.parametrize(
        "serializer_code",
        [
            "output = value\nreturn output",
            ["output = value", "return output"],
        ],
        ids=["string", "list"],
    )
    def test_add_serializer_multiline_code(
        self,
        serializer_code: str | list[str],
    ) -> None:
        """Test adding a custom serializer with multi-line code."""
        customizer = GAPICustomizer()
        customizer.add_custom_serializer(
            field_name="string",
            serializer_code=serializer_code,
            output_type="str",
            class_name="Model",
        )
        gapi = GAPI(customizer=customizer)
        gapi.add_object_from_dict({"string": "string"})
        content = gapi.get_required_models_content()
        assert (
            """    @field_serializer('string')
    def serialize_string(self, value: str) -> str:
        output = value
        return output"""
            in content
        )

    def test_add_serializer_to_all_classes(self) -> None:
        """Test adding custom serializers to all classes."""
        customizer = GAPICustomizer()
        customizer.add_custom_serializer(
            field_name="string",
            serializer_code="return",
            output_type="str",
        )
        gapi = GAPI(customizer=customizer)
        gapi.add_object_from_dict(
            {
                "class1": {
                    "string": "string",
                },
                "class2": {
                    "string": "string",
                },
            },
        )
        content = gapi.get_required_models_content()
        assert (
            """    @field_serializer('string')
    def serialize_string(self, value: str) -> str:
        return"""
            in content
        )
        assert content.count("@field_serializer('string')") == 2  # noqa: PLR2004


class TestAddImports:
    """Test add_import."""

    def test_add_import(self) -> None:
        """Test that additional imports are inserted at the top of the module."""
        customizer = GAPICustomizer()
        customizer.add_additional_import("from pydantic import NaiveDatetime")
        customizer.add_replacement_field(
            class_name="Model",
            field_name="string",
            new_field="string: NaiveDatetime",
        )
        gapi = GAPI(customizer=customizer)
        gapi.add_object_from_dict({"string": "string"})
        lines = gapi.get_required_models_content().splitlines()
        assert lines[0] == "from pydantic import NaiveDatetime"


class TestReplaceUntypedList:
    """Test that empty lists are typed as list[None] instead of list[Any]."""

    def test_empty_list(self) -> None:
        """Test that an empty list is typed as list[None]."""
        gapi = GAPI()
        gapi.add_object_from_dict({"items": []})
        lines = gapi.get_required_models_content().splitlines()
        assert "    items: list[None]" in lines


class TestClassName:
    """Test custom class_name parameter."""

    def test_custom_class_name(self) -> None:
        """Test that class_name sets the root model class name."""
        gapi = GAPI(class_name="CustomModel")
        gapi.add_object_from_dict({"key": "value"})
        lines = gapi.get_required_models_content().splitlines()
        assert "class CustomModel(BaseModel):" in lines
        assert "class Model(BaseModel):" not in lines


class TestRuntimeAnnotationImports:
    """Test that annotation-type imports stay at runtime, not under TYPE_CHECKING."""

    def test_uuid_field_builds_and_validates(self) -> None:
        """A UUID-typed model imports UUID at runtime and validates without rebuild."""
        sample = {"x_api_key": "3e4666bf-d5e5-4aa7-b8ce-cefe41c7568a"}
        gapi = GAPI(class_name="SearchModel")
        gapi.add_object_from_dict(sample)
        content = gapi.get_required_models_content()

        assert "from uuid import UUID" in content
        assert "TYPE_CHECKING" not in content

        # Exec the generated module and validate a sample. This fails with
        # PydanticUserError if UUID was relocated under TYPE_CHECKING.
        namespace: dict[str, Any] = {}
        exec(content, namespace)  # noqa: S102
        namespace["SearchModel"].model_validate(sample)


class TestNarrowStringUnions:
    """Test that widening a narrow string field keeps the narrow type usable."""

    def test_uuid_or_str_field_preserves_uuid(self) -> None:
        """A field seen as both a UUID and an arbitrary string keeps both.

        The first object types `target_id` as a UUID; the second widens it with
        a non-UUID string. Without a left-to-right union the smart union would
        resolve every value to `str`, discarding the UUID type.
        """
        gapi = GAPI(class_name="SearchModel")
        gapi.add_object_from_dict({"target_id": "05eb6a8e-90ed-4947-8c0b-e6536cbddd5f"})
        gapi.add_object_from_dict({"target_id": "laliga-on-espn-plus"})
        content = gapi.get_required_models_content()

        assert "target_id: UUID | str = Field(union_mode='left_to_right')" in content

        namespace: dict[str, Any] = {}
        exec(content, namespace)  # noqa: S102
        model = namespace["SearchModel"]
        uuid_value = model.model_validate(
            {"target_id": "05eb6a8e-90ed-4947-8c0b-e6536cbddd5f"},
        ).target_id
        str_value = model.model_validate({"target_id": "814"}).target_id
        assert type(uuid_value).__name__ == "UUID"
        assert type(str_value) is str


class TestDatetimeAwareness:
    """Test that naive and timezone-aware datetimes get distinct types."""

    def test_naive_datetime_is_not_aware(self) -> None:
        """A datetime without an offset is typed as `NaiveDatetime`."""
        gapi = GAPI()
        gapi.add_object_from_dict({"validity_end_time": "2026-12-31T23:59:59"})
        lines = gapi.get_required_models_content().splitlines()
        assert "    validity_end_time: NaiveDatetime" in lines

    def test_aware_datetime_is_aware(self) -> None:
        """A datetime with an offset is typed as `AwareDatetime`."""
        gapi = GAPI()
        gapi.add_object_from_dict({"validity_end_time": "2026-12-31T23:59:59Z"})
        lines = gapi.get_required_models_content().splitlines()
        assert "    validity_end_time: AwareDatetime" in lines

    @pytest.mark.parametrize(
        "values",
        [
            ("2026-12-31T23:59:59", "2026-12-31T23:59:59Z"),
            ("2026-12-31T23:59:59Z", "2026-12-31T23:59:59"),
        ],
        ids=["naive_first", "aware_first"],
    )
    def test_mixed_datetimes_accept_both(self, values: tuple[str, str]) -> None:
        """A field seen as both naive and aware validates either form."""
        gapi = GAPI(class_name="ContentModel")
        for value in values:
            gapi.add_object_from_dict({"validity_end_time": value})
        content = gapi.get_required_models_content()

        namespace: dict[str, Any] = {}
        exec(content, namespace)  # noqa: S102
        model = namespace["ContentModel"]
        naive = model.model_validate({"validity_end_time": values[0]})
        aware = model.model_validate({"validity_end_time": values[1]})
        assert (naive.validity_end_time.tzinfo is None) == (
            values[0] == "2026-12-31T23:59:59"
        )
        assert (aware.validity_end_time.tzinfo is None) == (
            values[1] == "2026-12-31T23:59:59"
        )


class TestFalseConvertFlag:
    """Test the convert parameter."""

    def test_convert_false_keeps_strings(self) -> None:
        """Test that convert=False keeps date-like strings as strings."""
        gapi = GAPI(convert=False)
        gapi.add_object_from_dict({"date_field": "2000-01-01"})
        lines = gapi.get_required_models_content().splitlines()
        assert "    date_field: str" in lines


class TestGetJsonSchema:
    """Test get_json_schema_content."""

    def test_json_schema_content(self) -> None:
        """Test that JSON schema is generated from object data."""
        gapi = GAPI()
        gapi.add_object_from_dict({"name": "test", "count": 42})
        expected = {
            "$schema": "http://json-schema.org/schema#",
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["count", "name"],
        }
        assert json.loads(gapi.get_json_schema_content()) == expected

    def test_json_schema_from_schema_file(self) -> None:
        """Test that loading a schema round-trips through get_json_schema_content."""
        gapi = GAPI()
        gapi.add_schema_from_file(SCHEMA_PATH)
        assert json.loads(gapi.get_json_schema_content()) == json.loads(
            SCHEMA_PATH.read_text(),
        )


class TestWriteToFile:
    """Test write methods."""

    def test_write_json_schema_to_file(self, tmp_path: Path) -> None:
        """Test writing JSON schema to a file."""
        gapi = GAPI()
        gapi.add_object_from_dict({"key": "value"})
        output = tmp_path / "output" / "schema.json"
        gapi.write_json_schema_to_file(output)
        assert output.read_text() == gapi.get_json_schema_content() + "\n"

    def test_write_required_models_to_file(self, tmp_path: Path) -> None:
        """Test writing Pydantic model to a file."""
        gapi = GAPI()
        gapi.add_object_from_dict({"key": "value"})
        output = tmp_path / "output" / "model.py"
        gapi.write_required_models_to_file(output)
        assert output.read_text() == gapi.get_required_models_content()


class TestCaching:
    """Test caching behavior of GAPI."""

    def test_required_models_are_cached(self) -> None:
        """Test that calling get_required_models_content twice returns same result."""
        gapi = GAPI()
        gapi.add_object_from_dict({"key": "value"})
        first = gapi.get_required_models_content()
        second = gapi.get_required_models_content()
        assert first is second

    def test_cache_invalidated_on_new_object(self) -> None:
        """Test that adding a new object invalidates the cache."""
        gapi = GAPI()
        gapi.add_object_from_dict({"key": "value"})
        first = gapi.get_required_models_content()
        gapi.add_object_from_dict({"new_key": 123})
        second = gapi.get_required_models_content()
        assert first is not second
        assert "    new_key: int | None = None" in second.splitlines()

    def test_cache_invalidated_on_new_schema(self) -> None:
        """Test that adding a new schema invalidates the cache."""
        gapi = GAPI()
        gapi.add_object_from_dict({"key": "value"})
        first = gapi.get_required_models_content()
        gapi.add_schema_from_dict(json.loads(SCHEMA_PATH.read_text()))
        second = gapi.get_required_models_content()
        assert first is not second


# TODO: Validate
class TestRawInput:
    """Test the raw_input property added to the root model."""

    # TODO: Validate
    def test_root_model_keeps_raw_input(self) -> None:
        """The root model holds the data it was validated from."""
        sample = {"total": 1, "data": [{"id": "abc"}]}
        gapi = GAPI(class_name="ArtistModel")
        gapi.add_object_from_dict(sample)

        namespace: dict[str, Any] = {}
        exec(gapi.get_required_models_content(), namespace)  # noqa: S102
        model = namespace["ArtistModel"].model_validate(sample)

        assert model.raw_input == sample
        assert not hasattr(model.data[0], "raw_input")

    # TODO: Validate
    def test_optional_model_keeps_raw_input(self) -> None:
        """The all-optional copy of the root model holds it too."""
        sample = {"total": 1, "data": [{"id": "abc"}]}
        gapi = GAPI(class_name="ArtistModel")
        gapi.add_object_from_dict(sample)

        namespace: dict[str, Any] = {}
        exec(gapi.get_optional_models_content(), namespace)  # noqa: S102
        drifted = {"total": 2, "unexpected": True}
        model = namespace["ArtistModel"].model_validate(drifted)

        assert model.raw_input == drifted

    # TODO: Validate
    def test_own_raw_input_field_is_kept(self) -> None:
        """A response with its own raw_input field keeps that field."""
        gapi = GAPI(class_name="ArtistModel")
        gapi.add_object_from_dict({"raw_input": "value"})
        content = gapi.get_required_models_content()

        assert "    raw_input: str" in content.splitlines()
        assert "PrivateAttr" not in content
