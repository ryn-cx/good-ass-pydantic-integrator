# TODO: Validate
"""Rebuild a package's models from the responses recorded for them.

Every model is rewritten, so what the models say is always what the whole
recorded corpus says.

Four files are written per model. `strict_models.py` is the model as the
recordings describe it, `optional_models.py` is the same model with every field
optional, `models.json` is the schema they were built from, and `models.py`
picks between the two: a type checker reads the strict one, and the running
program reads the all-optional one, so a response that has drifted still parses.

A model is built from every response recorded for it: the ones in
`<files_path>/<ModelName>` and the pages of each walk in
`<files_path>/Multipages/<ModelName>`, which are read with the same model. What
is under `<files_path>/Errors` is what the API answers when it finds nothing, so
it is not a response the model reads and is left out.

`recorded_model_names` lists what has recordings; `generate_model` rebuilds one.
"""

from __future__ import annotations

import ast
import json
import logging
from typing import TYPE_CHECKING

from good_ass_pydantic_integrator.gapi import GAPI

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from good_ass_pydantic_integrator.constants import JSON_VALUE

logger = logging.getLogger(__name__)

SKIPPED_DIRECTORIES = frozenset({"Multipages", "Errors"})
"""Directories under the recordings that are not a model's own responses."""

MINIMUM_COMPARABLE_RECORDINGS = 2
"""How many recordings there has to be before one of them can be spare."""


# TODO: Validate
def model_directory(package_path: Path, model_name: str) -> Path:
    """Return the package directory a model's files are written to.

    Args:
        package_path: The package the models are written into.
        model_name: The model class name, e.g. `SearchEpisodeModel`.

    Returns:
        The directory holding that model's `strict_models.py`.

    Raises:
        FileNotFoundError: If no package under `package_path` defines that model.
    """
    for models_file in package_path.rglob("strict_models.py"):
        if f"class {model_name}(" in models_file.read_text():
            return models_file.parent
    msg = f"No package under {package_path} defines {model_name}"
    raise FileNotFoundError(msg)


# TODO: Validate
def recording_paths(files_path: Path, model_name: str) -> list[Path]:
    """Return every recording a model is built from, walks last."""
    responses = sorted((files_path / model_name).glob("*"))
    walks = sorted((files_path / "Multipages" / model_name).glob("*"))
    return [path for path in responses + walks if path.is_file()]


# TODO: Validate
def responses_in(
    recording: Path,
    read: Callable[[str], JSON_VALUE],
) -> list[JSON_VALUE]:
    """Return the responses one recording holds.

    A walk is recorded as the list of pages it was served, and each page is read
    with the same model, so each is its own response here.
    """
    parsed = read(recording.read_text())
    is_walk = recording.parent.parent.name == "Multipages"
    if is_walk and isinstance(parsed, list):
        return list(parsed)
    return [parsed]


# TODO: Validate
def recorded_responses(
    files_path: Path,
    model_name: str,
    read: Callable[[str], JSON_VALUE],
) -> Iterator[JSON_VALUE]:
    """Yield every recorded response a model is built from.

    Args:
        files_path: Where the recorded responses live.
        model_name: The model class name, e.g. `SeriesModel`.
        read: Turns a recording into the object the model reads.

    Yields:
        Each recorded response, and each page of each recorded walk.
    """
    for recording in recording_paths(files_path, model_name):
        yield from responses_in(recording, read)


# TODO: Validate
def schema_of(recordings: list[Path], read: Callable[[str], JSON_VALUE]) -> str:
    """Return the schema a set of recordings describes."""
    gapi = GAPI()
    for recording in recordings:
        for response in responses_in(recording, read):
            gapi.add_object_from_dict(response)
    return gapi.get_json_schema_content()


# TODO: Validate
def redundant_recordings(
    files_path: Path,
    model_name: str,
    read: Callable[[str], JSON_VALUE] = json.loads,
) -> list[Path]:
    """Return the recordings that describe nothing the others do not.

    Dropped one at a time, so what is left still describes the whole schema. Two
    recordings that say the same thing leave one of them here and keep the other.

    Args:
        files_path: Where the recorded responses live.
        model_name: The model class name, e.g. `SeriesModel`.
        read: Turns a recording into the object the model reads.

    Returns:
        The recordings that can be deleted without changing the model.
    """
    recordings = recording_paths(files_path, model_name)
    if len(recordings) < MINIMUM_COMPARABLE_RECORDINGS:
        return []

    whole_schema = schema_of(recordings, read)
    kept = list(recordings)
    redundant: list[Path] = []
    for recording in recordings:
        without = [path for path in kept if path != recording]
        if without and schema_of(without, read) == whole_schema:
            kept = without
            redundant.append(recording)
    return redundant


# TODO: Validate
def log_redundant_recordings(
    files_path: Path,
    model_name: str,
    read: Callable[[str], JSON_VALUE] = json.loads,
) -> None:
    """Log the recordings a model does not need."""
    for recording in redundant_recordings(files_path, model_name, read):
        logger.info(
            "%s does not need %s.",
            model_name,
            recording.relative_to(files_path),
        )


# TODO: Validate
def recorded_model_names(files_path: Path) -> list[str]:
    """Return the name of every model that has responses recorded for it."""
    return sorted(
        directory.name
        for directory in files_path.iterdir()
        if directory.is_dir() and directory.name not in SKIPPED_DIRECTORIES
    )


# TODO: Validate
def model_names(models_file: Path) -> set[str]:
    """Return the name of every model class a generated file defines."""
    return {
        node.name
        for node in ast.parse(models_file.read_text()).body
        if isinstance(node, ast.ClassDef)
    }


# TODO: Validate
def drop_names_missing_from_optional_models(directory: Path) -> None:
    """Remove the names `models.py` lists that the all-optional model does not define.

    Making every field optional makes two models the strict model keeps apart
    identical, and only one of them is written, so `models.py` is left naming a
    class that is not there and the package stops importing.
    """
    models_file = directory / "models.py"
    dropped = model_names(directory / "strict_models.py") - model_names(
        directory / "optional_models.py",
    )
    if not dropped:
        return
    kept_lines = [
        line
        for line in models_file.read_text().splitlines(keepends=True)
        if line.strip().rstrip(",").strip('"') not in dropped
    ]
    models_file.write_text("".join(kept_lines))


# TODO: Validate
def generate_model(
    files_path: Path,
    package_path: Path,
    model_name: str,
    read: Callable[[str], JSON_VALUE] = json.loads,
) -> None:
    """Write the schema and models for one model from its recorded responses.

    Args:
        files_path: Where the recorded responses live.
        package_path: The package the models are written into. Given as a path
            rather than an import, so this still runs when the model it is
            about to rewrite is what stops the package importing.
        model_name: The model class name, e.g. `SeriesModel`.
        read: Turns a recording into the object the model reads.
    """
    gapi = GAPI(model_name)
    responses = list(recorded_responses(files_path, model_name, read))
    if not responses:
        logger.warning("Nothing recorded for %s, leaving it alone.", model_name)
        return

    for response in responses:
        gapi.add_object_from_dict(response)

    directory = model_directory(package_path, model_name)
    logger.info("Writing %s from %s responses.", model_name, len(responses))
    gapi.write_json_schema_to_file(directory / "models.json")
    gapi.write_strict_models_to_file(directory / "strict_models.py")
    gapi.write_optional_models_to_file(directory / "optional_models.py")
    gapi.write_models_to_file(directory / "models.py")
    drop_names_missing_from_optional_models(directory)
    log_redundant_recordings(files_path, model_name, read)
