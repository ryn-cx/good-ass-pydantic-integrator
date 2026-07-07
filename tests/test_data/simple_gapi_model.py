# ruff: noqa: D100, D101
from pydantic import AwareDatetime, ConfigDict

from good_ass_pydantic_integrator import GAPIBaseModel


class SimpleGapiModel(GAPIBaseModel):
    model_config = ConfigDict(extra="forbid")
    created_at: AwareDatetime
