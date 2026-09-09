# TODO: Validate
"""Helpers for putting a downloaded response where the generator reads it.

A package that generates models keeps its recordings, the ids they were
downloaded with, and the package they are written into under one
`GeneratorPaths`, and one module per model named `_generate_<module>.py`.
"""

from __future__ import annotations

import json
import logging
import pkgutil
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING

from good_ass_pydantic_integrator.generate import (
    generate_model,
    redundant_recordings,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from types import ModuleType

    from good_ass_pydantic_integrator.constants import JSON_VALUE

logger = logging.getLogger(__name__)

type Id = str | int | tuple[str | int | None, ...] | None
"""One id, which is what a response is downloaded with."""

type Ids = Sequence[Id] | Mapping[str, Id]
"""The ids a model's responses are recorded for.

A mapping is what a model whose recordings are named uses, keyed by that name.
"""

MODULE_PREFIX = "_generate_"
"""What the name of a module that rebuilds a model starts with."""

RECORDING_SUFFIX = ".json"
"""What a recorded response is named with."""


# TODO: Validate
@dataclass(frozen=True)
class GeneratorPaths:
    """Where one package's recordings, ids and generated models live.

    Args:
        files_path: Where the recorded responses live.
        ids_path: Where the ids each model's responses are recorded for live.
        package_path: The package the models are written into.
    """

    files_path: Path
    ids_path: Path
    package_path: Path

    # TODO: Validate
    def recorded_path(
        self,
        model_name: str,
        name: str | int,
        suffix: str = RECORDING_SUFFIX,
    ) -> Path:
        """Return where the response for `name` is recorded."""
        return self.files_path / model_name / f"{sanitized_file_name(name)}{suffix}"

    # TODO: Validate
    def ids_file_path(self, model_name: str) -> Path:
        """Return where the ids a model's responses are recorded for live."""
        return self.ids_path / f"{model_name}.json"


# TODO: Validate
def sanitized_file_name(name: str | int) -> str:
    """Sanitize a string or integer into a valid file name."""
    sanitized = re.compile(r'[<>:"/\|?*\x00-\x1f]').sub("_", str(name)).rstrip(". ")
    return sanitized or "_"


# TODO: Validate
def download_if_missing(
    paths: GeneratorPaths,
    model_name: str,
    name: str | int,
    download: Callable[[], str],
    suffix: str = RECORDING_SUFFIX,
) -> None:
    """Download a response into `_files` if it does not exist."""
    recorded_path = paths.recorded_path(model_name, name, suffix)
    if recorded_path.exists():
        return
    logger.info("Downloading %s/%s.", model_name, name)
    recorded_path.parent.mkdir(parents=True, exist_ok=True)
    recorded_path.write_text(download(), encoding="utf-8")


# TODO: Validate
def read_id(entry: object) -> Id:
    """Return one id as the generator reads it.

    An id written as a list is read back as a tuple, which is how an id made of
    more than one value is given.
    """
    return tuple(entry) if isinstance(entry, list) else entry


# TODO: Validate
def written_id(id_: Id) -> object:
    """Return one id as the file holds it."""
    return list(id_) if isinstance(id_, tuple) else id_


# TODO: Validate
def load_ids(paths: GeneratorPaths, model_name: str) -> Ids:
    """Return the ids a model's responses are recorded for.

    A file holding an object is read back as a mapping of the name each response
    is recorded under to the id it is downloaded with.
    """
    entries = json.loads(paths.ids_file_path(model_name).read_text(encoding="utf-8"))
    if isinstance(entries, dict):
        return {name: read_id(entry) for name, entry in entries.items()}
    return [read_id(entry) for entry in entries]


# TODO: Validate
def save_ids(paths: GeneratorPaths, model_name: str, ids: Ids) -> None:
    """Write the ids a model's responses are recorded for."""
    ids_file_path = paths.ids_file_path(model_name)
    ids_file_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(ids, Mapping):
        entries: object = {name: written_id(id_) for name, id_ in ids.items()}
    else:
        entries = [written_id(id_) for id_ in ids]
    ids_file_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


# TODO: Validate
def drop_redundant_recordings(
    paths: GeneratorPaths,
    model_name: str,
    read: Callable[[str], JSON_VALUE] = json.loads,
    name_of: Callable[[Id], str] = str,
    suffix: str = RECORDING_SUFFIX,
) -> None:
    """Delete the recordings a model does not need, and the ids they came from.

    A recording the ids file does not name is deleted as well, since nothing
    downloads it again.

    Args:
        paths: Where the recordings and ids live.
        model_name: The model class name, e.g. `SeriesModel`.
        read: Turns a recording into the object the model reads.
        name_of: Returns the name an id is recorded under, for an id that is not
            the name itself.
        suffix: What a recorded response is named with.
    """
    if not paths.ids_file_path(model_name).exists():
        return

    ids = load_ids(paths, model_name)
    if isinstance(ids, Mapping):
        recorded_names = {sanitized_file_name(name) for name in ids}
    else:
        recorded_names = {sanitized_file_name(name_of(id_)) for id_ in ids}

    redundant = [
        recording
        for recording in redundant_recordings(paths.files_path, model_name, read)
        if recording.stem in recorded_names
    ]
    unlisted = [
        recording
        for recording in (paths.files_path / model_name).glob(f"*{suffix}")
        if recording.stem not in recorded_names
    ]
    if not redundant and not unlisted:
        return

    for recording in redundant + unlisted:
        logger.info("Dropping %s.", recording.relative_to(paths.files_path))
        recording.unlink()

    dropped = {recording.stem for recording in redundant}
    if isinstance(ids, Mapping):
        kept: Ids = {
            name: id_
            for name, id_ in ids.items()
            if sanitized_file_name(name) not in dropped
        }
    else:
        kept = [id_ for id_ in ids if sanitized_file_name(name_of(id_)) not in dropped]
    save_ids(paths, model_name, kept)


# TODO: Validate
def rebuild_model(
    paths: GeneratorPaths,
    model_name: str,
    read: Callable[[str], JSON_VALUE] = json.loads,
    name_of: Callable[[Id], str] = str,
    suffix: str = RECORDING_SUFFIX,
) -> None:
    """Rewrite a model from its recordings, then drop the ones it does not need.

    A model that needs a customizer calls `generate_model` and
    `drop_redundant_recordings` itself, since the customizer does not fit here.
    """
    generate_model(paths.files_path, paths.package_path, model_name, read)
    drop_redundant_recordings(paths, model_name, read, name_of, suffix)


# TODO: Validate
def model_module_names(
    package: ModuleType,
    prefix: str = MODULE_PREFIX,
) -> list[str]:
    """Return the name of every module in `package` that rebuilds a model."""
    return sorted(
        module.name
        for module in pkgutil.iter_modules(package.__path__)
        if module.name.startswith(prefix)
    )


# TODO: Validate
def generate_all(
    package: ModuleType,
    client: object,
    prefix: str = MODULE_PREFIX,
) -> None:
    """Rebuild every model in `package`, one module at a time.

    A module named `_generate_<module>.py` holds a `generate_<module>` function,
    which is handed the client the responses are downloaded with.
    """
    for module_name in model_module_names(package, prefix):
        module = import_module(f"{package.__name__}.{module_name}")
        getattr(module, module_name.removeprefix("_"))(client)
