"""Utilities for working with GAPIClients."""

import importlib
import pkgutil
from typing import TYPE_CHECKING, Any

from good_ass_pydantic_integrator.gapi_client import GAPIClient

if TYPE_CHECKING:
    from types import ModuleType


def response_models(package: ModuleType) -> list[type[GAPIClient[Any]]]:
    """Returns a list of all of the response models for DivingBoard."""
    for info in pkgutil.walk_packages(
        package.__path__,
        package.__name__ + ".",
    ):
        importlib.import_module(info.name)

    def _collect(cls: type) -> list[type[GAPIClient[Any]]]:
        result: list[type[GAPIClient[Any]]] = []
        for sub in cls.__subclasses__():
            if getattr(sub, "_response_model", None):
                result.append(sub)
            result.extend(_collect(sub))
        return result

    return _collect(GAPIClient)


def remove_redundant_files(package: ModuleType) -> None:
    """Remove redundant JSON files for all response models in the given package."""
    for response_model in response_models(package):
        response_model.remove_redundant_json_files()


def rebuild_models(package: ModuleType) -> None:
    """Rebuild all response models in the given package."""
    for response_model in response_models(package):
        response_model.rebuild_model()
