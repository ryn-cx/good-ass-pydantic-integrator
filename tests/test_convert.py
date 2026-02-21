"""Test converting values."""

import ipaddress
import uuid
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

import pytest

from good_ass_pydantic_integrator.convert import convert_input_data, convert_value

if TYPE_CHECKING:
    from good_ass_pydantic_integrator.constants import INPUT_TYPE

CONVERSION_CASES = [
    ("2018-11-13T20:20:39+08:00", datetime),
    ("2018-11-13T20:20:39Z", datetime),
    ("2018-11-13T20:20:39", datetime),
    ("2018-11-13", date),
    ("20:20:39", time),
    ("P3D", timedelta),
    ("192.168.1.1", ipaddress.IPv4Address),
    ("::1", ipaddress.IPv6Address),
    ("3e4666bf-d5e5-4aa7-b8ce-cefe41c7568a", uuid.UUID),
    ("String", str),
    ("123", str),
    ("123.45", str),
]


class TestConvertValue:
    """Test convert_value function."""

    @pytest.mark.parametrize(("input_data", "expected_type"), CONVERSION_CASES)
    def test_convert_value(self, *, input_data: str, expected_type: type) -> None:
        """Test converting a single value."""
        assert type(convert_value(input_data)) is expected_type


class TestConvertInputData:
    """Test convert_input_data function."""

    @pytest.mark.parametrize(("input_data", "expected_type"), CONVERSION_CASES)
    def test_convert_dict(
        self,
        *,
        input_data: str,
        expected_type: type,
    ) -> None:
        """Test converting values in dict."""
        dict_input: INPUT_TYPE = {"key_1": input_data}
        dict_input = convert_input_data(dict_input)
        assert type(dict_input) is dict
        assert type(dict_input["key_1"]) is expected_type

    @pytest.mark.parametrize(("input_data", "expected_type"), CONVERSION_CASES)
    def test_convert_list(
        self,
        *,
        input_data: str,
        expected_type: type,
    ) -> None:
        """Test converting values in list."""
        list_input: INPUT_TYPE = [input_data]
        list_input = convert_input_data(list_input)
        assert type(list_input) is list
        assert type(list_input[0]) is expected_type

    @pytest.mark.parametrize(("input_data", "expected_type"), CONVERSION_CASES)
    def test_convert_nested_dict(
        self,
        *,
        input_data: str,
        expected_type: type,
    ) -> None:
        """Test converting values in nested dict."""
        nested_dict_input: INPUT_TYPE = {
            "key_1": input_data,
            "key_2": {"key_3": input_data},
        }
        nested_dict_input = convert_input_data(nested_dict_input)
        assert type(nested_dict_input) is dict
        assert type(nested_dict_input["key_1"]) is expected_type
        assert type(nested_dict_input["key_2"]) is dict
        assert type(nested_dict_input["key_2"]["key_3"]) is expected_type

    @pytest.mark.parametrize(("input_data", "expected_type"), CONVERSION_CASES)
    def test_convert_nested_list(
        self,
        *,
        input_data: str,
        expected_type: type,
    ) -> None:
        """Test converting values in nested list."""
        nested_list_input: INPUT_TYPE = [input_data, [input_data]]
        nested_list_input = convert_input_data(nested_list_input)
        assert type(nested_list_input) is list
        assert type(nested_list_input[0]) is expected_type
        assert type(nested_list_input[1]) is list
        assert type(nested_list_input[1][0]) is expected_type

    @pytest.mark.parametrize(("input_data", "expected_type"), CONVERSION_CASES)
    def test_convert_list_with_dict(
        self,
        *,
        input_data: str,
        expected_type: type,
    ) -> None:
        """Test converting values in a list containing a dict."""
        list_with_dict: INPUT_TYPE = [input_data, {"key": input_data}]
        list_with_dict = convert_input_data(list_with_dict)
        assert type(list_with_dict) is list
        assert type(list_with_dict[0]) is expected_type
        assert type(list_with_dict[1]) is dict
        assert type(list_with_dict[1]["key"]) is expected_type

    @pytest.mark.parametrize(("input_data", "expected_type"), CONVERSION_CASES)
    def test_convert_dict_with_list(
        self,
        *,
        input_data: str,
        expected_type: type,
    ) -> None:
        """Test converting values in a dict containing a list."""
        dict_with_list: INPUT_TYPE = {"key": input_data, "list": [input_data]}
        dict_with_list = convert_input_data(dict_with_list)
        assert type(dict_with_list) is dict
        assert type(dict_with_list["key"]) is expected_type
        assert type(dict_with_list["list"]) is list
        assert type(dict_with_list["list"][0]) is expected_type
