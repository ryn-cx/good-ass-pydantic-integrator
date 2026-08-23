# TODO: Validate
"""Good Ass Pydantic Integrator constants ."""

import ipaddress
import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta

type MAIN_TYPE = (
    datetime
    | date
    | time
    | timedelta
    | ipaddress.IPv4Address
    | ipaddress.IPv6Address
    | uuid.UUID
    | str
    | int
    | float
    | bool
    | None
)
type JSON_VALUE = MAIN_TYPE | Mapping[str, JSON_VALUE] | Sequence[JSON_VALUE]
type INPUT_TYPE = Mapping[str, JSON_VALUE] | Sequence[JSON_VALUE]

BLANK_MODEL_TEMPLATE = """# ruff: noqa: D100, D101
from good_ass_pydantic_integrator import GAPIBaseModel
from pydantic import ConfigDict


class {class_name}(GAPIBaseModel):
    model_config = ConfigDict(extra="forbid")
"""

MODELS_TEMPLATE = '''"""{class_name}, strict to a type checker, all-optional at runtime.

A type checker reads the strict model, so every field carries the type and
the requiredness the schema recorded. At runtime the all-optional copy is imported
instead, so a response that has drifted still parses and a field the data is
missing is None despite what its type hint says.
"""

from typing import TYPE_CHECKING

from good_ass_pydantic_integrator import load

from {optional_module} import {class_name} as OptionalModel
from {strict_module} import {class_name} as StrictModel

if TYPE_CHECKING:
    from {strict_module} import (
{names}    )
else:
    from {optional_module} import (
{names}    )

__all__ = [
{exports}    "model_validate_json",
]


def model_validate_json(data: str | bytes | object, log_id: str) -> {class_name}:
    """Read a downloaded file into {class_name}."""
    return load.model_validate_json(StrictModel, OptionalModel, data, log_id)
'''
