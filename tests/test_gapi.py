"""Test GAPI."""

import json
from typing import TYPE_CHECKING

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
        assert gapi.get_pydantic_model_content() == MODEL_PATH.read_text()


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
        assert gapi.get_pydantic_model_content() == MODEL_PATH.read_text()


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
        lines = gapi.get_pydantic_model_content().splitlines()
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
        content = gapi.get_pydantic_model_content()
        assert (
            """    integer_that_is_stored_as_a_string: int = Field(
        ...,
        alias="IntegerThatIsStoredAsAString",
    )"""
            in content
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
        lines = gapi.get_pydantic_model_content().splitlines()
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
        content = gapi.get_pydantic_model_content()
        assert (
            """    integer_that_is_stored_as_a_string: int = Field(
        ...,
        alias="IntegerThatIsStoredAsAString",
    )"""
            in content
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
        content = gapi.get_pydantic_model_content()
        assert (
            """    @field_serializer("string")
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
        content = gapi.get_pydantic_model_content()
        assert (
            """    @field_serializer("string")
    def serialize_string(self, value: str) -> str:
        return output"""
            in content
        )
        assert (
            """    @field_serializer("string2")
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
        content = gapi.get_pydantic_model_content()
        assert (
            """    @field_serializer("string")
    def serialize_string(self, value: str) -> str:
        return value"""
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
        content = gapi.get_pydantic_model_content()
        assert (
            """    @field_serializer("string")
    def serialize_string(self, value: str) -> str:
        return"""
            in content
        )
        assert content.count('@field_serializer("string")') == 2  # noqa: PLR2004


class TestAddImports:
    """Test add_import."""

    def test_add_import(self) -> None:
        """Test adding custom imports after the filename comment line."""
        customizer = GAPICustomizer()
        customizer.add_additional_import("from pydantic import NaiveDatetime")
        # Need to include a usage of NaiveDatetime to ensure the import is not
        # removed by ruff.
        customizer.add_replacement_field(
            class_name="Model",
            field_name="string",
            new_field="string: NaiveDatetime",
        )
        gapi = GAPI(customizer=customizer)
        gapi.add_object_from_dict({"string": "string"})
        lines = gapi.get_pydantic_model_content().splitlines()
        assert "from pydantic import BaseModel, ConfigDict, NaiveDatetime" in lines


class TestReplaceUntypedList:
    """Test that empty lists are typed as list[None] instead of list[Any]."""

    def test_empty_list(self) -> None:
        """Test that an empty list is typed as list[None]."""
        gapi = GAPI()
        gapi.add_object_from_dict({"items": []})
        lines = gapi.get_pydantic_model_content().splitlines()
        assert "    items: list[None]" in lines


class TestClassName:
    """Test custom class_name parameter."""

    def test_custom_class_name(self) -> None:
        """Test that class_name sets the root model class name."""
        gapi = GAPI(class_name="CustomModel")
        gapi.add_object_from_dict({"key": "value"})
        lines = gapi.get_pydantic_model_content().splitlines()
        assert "class CustomModel(BaseModel):" in lines
        assert "class Model(BaseModel):" not in lines


class TestFalseConvertFlag:
    """Test the convert parameter."""

    def test_convert_false_keeps_strings(self) -> None:
        """Test that convert=False keeps date-like strings as strings."""
        gapi = GAPI(convert=False)
        gapi.add_object_from_dict({"date_field": "2000-01-01"})
        lines = gapi.get_pydantic_model_content().splitlines()
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

    def test_write_pydantic_model_to_file(self, tmp_path: Path) -> None:
        """Test writing Pydantic model to a file."""
        gapi = GAPI()
        gapi.add_object_from_dict({"key": "value"})
        output = tmp_path / "output" / "model.py"
        gapi.write_pydantic_model_to_file(output)
        assert output.read_text() == gapi.get_pydantic_model_content()


class TestCaching:
    """Test caching behavior of GAPI."""

    def test_pydantic_model_is_cached(self) -> None:
        """Test that calling get_pydantic_model_content twice returns same result."""
        gapi = GAPI()
        gapi.add_object_from_dict({"key": "value"})
        first = gapi.get_pydantic_model_content()
        second = gapi.get_pydantic_model_content()
        assert first is second

    def test_cache_invalidated_on_new_object(self) -> None:
        """Test that adding a new object invalidates the cache."""
        gapi = GAPI()
        gapi.add_object_from_dict({"key": "value"})
        first = gapi.get_pydantic_model_content()
        gapi.add_object_from_dict({"new_key": 123})
        second = gapi.get_pydantic_model_content()
        assert first is not second
        assert "    new_key: int | None = None" in second.splitlines()

    def test_cache_invalidated_on_new_schema(self) -> None:
        """Test that adding a new schema invalidates the cache."""
        gapi = GAPI()
        gapi.add_object_from_dict({"key": "value"})
        first = gapi.get_pydantic_model_content()
        gapi.add_schema_from_dict(json.loads(SCHEMA_PATH.read_text()))
        second = gapi.get_pydantic_model_content()
        assert first is not second
