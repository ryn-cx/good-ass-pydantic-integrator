# ruff: noqa: D100, D101
from pydantic import ConfigDict

from good_ass_pydantic_integrator import GAPIBaseModel


class UserModel(GAPIBaseModel):
    model_config = ConfigDict(extra="forbid")
