"""Constants used throughout Good Ass Pydantic Integrator."""

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
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class {class_name}(BaseModel):
    model_config = ConfigDict(extra="forbid")
"""
