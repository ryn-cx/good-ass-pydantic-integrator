# ruff: noqa: D100, D101
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from datetime import date, time, timedelta
    from ipaddress import IPv4Address, IPv6Address
    from uuid import UUID


class FieldDict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_datetime: AwareDatetime = Field(..., alias="_datetime")
    field_date: date = Field(..., alias="_date")
    field_time: time = Field(..., alias="_time")
    field_timedelta: timedelta = Field(..., alias="_timedelta")
    field_ipv4: IPv4Address = Field(..., alias="_ipv4")
    field_ipv6: IPv6Address = Field(..., alias="_ipv6")
    field_uuid: UUID = Field(..., alias="_uuid")
    field_int: int = Field(..., alias="_int")
    field_float: float = Field(..., alias="_float")
    field_str: str = Field(..., alias="_str")
    field_bool: bool = Field(..., alias="_bool")
    field_list: list[AwareDatetime] = Field(..., alias="_list")
    field_dict: FieldDict = Field(..., alias="_dict")
    field_name_that_is_long_with_multiple_lines: str = Field(
        ...,
        alias="FieldNameThatIsLongWithMultipleLines",
    )
    mixed_numbers: list[int | float]
