# ruff: noqa: D100, D101, D102, TC001, TC002, TC003
from pydantic import ConfigDict, RootModel

from good_ass_pydantic_integrator import GAPIBaseModel


class SimpleGapiModelItem(GAPIBaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int


class SimpleGapiModel(RootModel[list[SimpleGapiModelItem]]):
    root: list[SimpleGapiModelItem]
