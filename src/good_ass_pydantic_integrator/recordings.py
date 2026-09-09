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
from dataclasses import dataclass
from functools import partial
from importlib import import_module
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, model_validator

from good_ass_pydantic_integrator.generate import (
    generate_model,
    redundant_recordings,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from pathlib import Path
    from types import ModuleType

    from good_ass_pydantic_integrator.constants import JSON_VALUE

logger = logging.getLogger(__name__)

type Entries = list[JSON_VALUE] | dict[str, JSON_VALUE]
"""The ids file, which writes one entry per response, named or in order."""

MODULE_PREFIX = "_generate_"
"""What the name of a module that rebuilds a model starts with."""

RECORDING_SUFFIX = ".json"
"""What a recorded response is named with."""


# TODO: Validate
class RecordingId[ClientT](BaseModel):
    """One id a response is downloaded with, and how to download it.

    A model names the parts of its id, and the ids file writes each id as one
    value, or as a list of them in the order the fields are declared.
    """

    model_config = ConfigDict(frozen=True)

    # TODO: Validate
    @model_validator(mode="before")
    @classmethod
    def read_entry(cls, entry: Any) -> Any:  # noqa: ANN401 - An entry is any JSON.
        """Read an id written as one value or a list into the fields it names."""
        if isinstance(entry, dict):
            return entry
        parts = entry if isinstance(entry, list) else [entry]
        return dict(zip(cls.model_fields, parts, strict=False))

    # TODO: Validate
    def parts(self) -> list[Any]:
        """Return what this id is made of, in the order the fields are declared."""
        return [getattr(self, field) for field in type(self).model_fields]

    # TODO: Validate
    def written_entry(self) -> Any:  # noqa: ANN401 - An entry is any JSON.
        """Return this id as the ids file writes it."""
        parts = self.parts()
        return parts[0] if len(parts) == 1 else parts

    # TODO: Validate
    def recording_name(self) -> str:
        """Return the name the response for this id is recorded under.

        A model whose recordings are not named after their id overrides this.
        """
        return "_".join(str(part) for part in self.parts() if part is not None)

    # TODO: Validate
    def download(self, client: ClientT) -> str:
        """Download the response for this id."""
        msg = f"{type(self).__name__} does not say how it is downloaded."
        raise NotImplementedError(msg)


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
    partial_path = recorded_path.with_name(recorded_path.name + ".partial")
    partial_path.write_text(download(), encoding="utf-8")
    partial_path.replace(recorded_path)


# TODO: Validate
def download_missing[ClientT](
    paths: GeneratorPaths,
    model_name: str,
    ids: Iterable[RecordingId[ClientT]],
    client: ClientT,
    suffix: str = RECORDING_SUFFIX,
) -> None:
    """Download the responses a model does not have recorded yet."""
    for id_ in ids:
        download_if_missing(
            paths,
            model_name,
            id_.recording_name(),
            partial(id_.download, client),
            suffix,
        )


# TODO: Validate
def download_named_missing[ClientT](
    paths: GeneratorPaths,
    model_name: str,
    ids: Mapping[str, RecordingId[ClientT]],
    client: ClientT,
    suffix: str = RECORDING_SUFFIX,
) -> None:
    """Download the responses a model does not have recorded yet, by name."""
    for name, id_ in ids.items():
        download_if_missing(
            paths,
            model_name,
            name,
            partial(id_.download, client),
            suffix,
        )


# TODO: Validate
def read_entries(paths: GeneratorPaths, model_name: str) -> Entries:
    """Return the ids file for a model, as it is written."""
    return json.loads(paths.ids_file_path(model_name).read_text(encoding="utf-8"))


# TODO: Validate
def load_ids[IdT: RecordingId[Any]](
    paths: GeneratorPaths,
    model_name: str,
    id_type: type[IdT],
) -> list[IdT]:
    """Return the ids a model's responses are downloaded with.

    Args:
        paths: Where the ids live.
        model_name: The model class name, e.g. `SeriesModel`.
        id_type: The model one id is read into.
    """
    entries = read_entries(paths, model_name)
    if isinstance(entries, dict):
        msg = f"The ids for {model_name} are named, so load_named_ids reads them."
        raise TypeError(msg)
    return [id_type.model_validate(entry) for entry in entries]


# TODO: Validate
def load_named_ids[IdT: RecordingId[Any]](
    paths: GeneratorPaths,
    model_name: str,
    id_type: type[IdT],
) -> dict[str, IdT]:
    """Return the ids a model's responses are downloaded with, keyed by name.

    Args:
        paths: Where the ids live.
        model_name: The model class name, e.g. `SeriesModel`.
        id_type: The model one id is read into.
    """
    entries = read_entries(paths, model_name)
    if not isinstance(entries, dict):
        msg = f"The ids for {model_name} are not named, so load_ids reads them."
        raise TypeError(msg)
    return {name: id_type.model_validate(entry) for name, entry in entries.items()}


# TODO: Validate
def write_entries(paths: GeneratorPaths, model_name: str, entries: Entries) -> None:
    """Write the ids file for a model."""
    ids_file_path = paths.ids_file_path(model_name)
    ids_file_path.parent.mkdir(parents=True, exist_ok=True)
    ids_file_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


# TODO: Validate
def save_ids(
    paths: GeneratorPaths,
    model_name: str,
    ids: Sequence[RecordingId[Any]],
) -> None:
    """Write the ids a model's responses are recorded for."""
    write_entries(paths, model_name, [id_.written_entry() for id_ in ids])


# TODO: Validate
def save_named_ids(
    paths: GeneratorPaths,
    model_name: str,
    ids: Mapping[str, RecordingId[Any]],
) -> None:
    """Write the ids a model's responses are recorded for, keyed by name."""
    write_entries(
        paths,
        model_name,
        {name: id_.written_entry() for name, id_ in ids.items()},
    )


# TODO: Validate
def drop_redundant_recordings[IdT: RecordingId[Any]](
    paths: GeneratorPaths,
    model_name: str,
    id_type: type[IdT],
    read: Callable[[str], JSON_VALUE] = json.loads,
    suffix: str = RECORDING_SUFFIX,
) -> None:
    """Delete the recordings a model does not need, and the ids they came from.

    A recording the ids file does not name is deleted as well, since nothing
    downloads it again.

    Args:
        paths: Where the recordings and ids live.
        model_name: The model class name, e.g. `SeriesModel`.
        id_type: The model one id is read into.
        read: Turns a recording into the object the model reads.
        suffix: What a recorded response is named with.
    """
    if not paths.ids_file_path(model_name).exists():
        return

    entries = read_entries(paths, model_name)
    if isinstance(entries, dict):
        named_ids = load_named_ids(paths, model_name, id_type)
        recorded_names = {sanitized_file_name(name) for name in named_ids}
    else:
        ids = load_ids(paths, model_name, id_type)
        recorded_names = {sanitized_file_name(id_.recording_name()) for id_ in ids}

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
    if isinstance(entries, dict):
        save_named_ids(
            paths,
            model_name,
            {
                name: id_
                for name, id_ in named_ids.items()
                if sanitized_file_name(name) not in dropped
            },
        )
    else:
        save_ids(
            paths,
            model_name,
            [
                id_
                for id_ in ids
                if sanitized_file_name(id_.recording_name()) not in dropped
            ],
        )


# TODO: Validate
def rebuild_model[IdT: RecordingId[Any]](
    paths: GeneratorPaths,
    model_name: str,
    id_type: type[IdT],
    read: Callable[[str], JSON_VALUE] = json.loads,
    suffix: str = RECORDING_SUFFIX,
) -> None:
    """Rewrite a model from its recordings, then drop the ones it does not need.

    A model that needs a customizer calls `generate_model` and
    `drop_redundant_recordings` itself, since the customizer does not fit here.
    """
    generate_model(paths.files_path, paths.package_path, model_name, read)
    drop_redundant_recordings(paths, model_name, id_type, read, suffix)


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
