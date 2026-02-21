"""Functions to automatically convert string values to more specific types."""

import contextlib
import ipaddress
import uuid
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, cast

from pydantic import TypeAdapter

if TYPE_CHECKING:
    from good_ass_pydantic_integrator.constants import INPUT_TYPE, MAIN_TYPE


# All types supported by genson's string format inference except re.pattern because
# there is no way to determine if a string is a regular expression or a string.
GENSON_STRING_TYPES: list[type] = [
    datetime,
    date,
    time,
    timedelta,
    ipaddress.IPv4Address,
    ipaddress.IPv6Address,
    uuid.UUID,
]


def convert_value(input_string: str) -> MAIN_TYPE:
    """Convert a string to a more specific type if possible.

    Args:
        input_string: The string value to convert.

    Returns:
        The converted value if successful, otherwise the original string.
    """
    # Try each genson-supported type and check if the original input can be recreated
    # from the parsed value using pydantic's JSON serialization.
    for target_type in GENSON_STRING_TYPES:
        with contextlib.suppress(ValueError):
            adapter = cast("TypeAdapter[MAIN_TYPE]", TypeAdapter(target_type))
            parsed = adapter.validate_python(input_string)
            if adapter.dump_python(parsed, mode="json") == input_string:
                return parsed

    return input_string


def _convert_single_value(value: MAIN_TYPE) -> MAIN_TYPE:
    """Convert a single value to a more specific type if possible.

    Args:
        value: The value to convert.

    Returns:
        The converted value.
    """
    if isinstance(value, str):
        return convert_value(value)
    if isinstance(value, (dict, list)):
        return convert_input_data(value)
    return value


def convert_input_data(input_data: INPUT_TYPE) -> INPUT_TYPE:
    """Recursively convert all values to more specific types if possible.

    Args:
        input_data: The data structure to convert values in.

    Returns:
        A new data structure with all convertible values converted.
    """
    if isinstance(input_data, dict):
        return {key: _convert_single_value(value) for key, value in input_data.items()}
    return [_convert_single_value(value) for value in input_data]
