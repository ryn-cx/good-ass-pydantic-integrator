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

MODELS_TEMPLATE = '''"""{class_name}, required to a type checker and all-optional at runtime.

A type checker reads the required model, so every field carries the type and
the requiredness the schema recorded. At runtime the all-optional copy is imported
instead, so a response that has drifted still parses and a field the data is
missing is None despite what its type hint says.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from {required_module} import (
{names}    )
else:
    from {optional_module} import (
{names}    )

__all__ = [
{exports}]
'''
