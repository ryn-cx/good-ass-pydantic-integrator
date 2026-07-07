# ruff: noqa: D100, D101
from good_ass_pydantic_integrator import GAPIBaseModel
from pydantic import ConfigDict


class SimpleGapiModel(GAPIBaseModel):
    model_config = ConfigDict(extra="forbid")
    string: str
