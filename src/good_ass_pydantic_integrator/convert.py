"""Contains convert_input_data which converts strings into more specific types."""

import contextlib
import ipaddress
import re
import uuid
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, cast

from pydantic import TypeAdapter

if TYPE_CHECKING:
    from good_ass_pydantic_integrator.constants import INPUT_TYPE, JSON_VALUE, MAIN_TYPE

# This is the only string format where date and datetime overlap.
# https://pydantic.dev/docs/validation/2.0/usage/types/datetime/
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _convert_value(input_string: str) -> MAIN_TYPE:
    """Convert a string to a more specific type if possible.

    Args:
        input_string: The string value to convert.

    Returns:
        The converted value if successful, otherwise the original string.
    """
    genson_types: list[type] = [
        # Datetime must be before date because it is a more precise type.
        datetime,
        date,
        time,
        timedelta,
        ipaddress.IPv4Address,
        ipaddress.IPv6Address,
        uuid.UUID,
    ]

    # int/float inside of a string should remain a string because if the value was
    # supposed to be an int/float it would already be one since it's a normal JSON
    # type.
    with contextlib.suppress(ValueError):
        float(input_string)
        return input_string

    for target_type in genson_types:
        with contextlib.suppress(ValueError):
            adapter = cast("TypeAdapter[MAIN_TYPE]", TypeAdapter(target_type))
            parsed = adapter.validate_python(input_string)

            # If the datetime was actually a date return a date instead.
            if isinstance(parsed, datetime) and DATE_REGEX.match(input_string):
                return parsed.date()

            return parsed

    return input_string


def _convert_single_value(value: JSON_VALUE) -> JSON_VALUE:
    if isinstance(value, str):
        return _convert_value(value)
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
