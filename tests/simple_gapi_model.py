# ruff: noqa: D100, D101
from pydantic import BaseModel, ConfigDict


class SimpleGapiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
