"""Constants for tests."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from good_ass_pydantic_integrator.constants import MAIN_TYPE

TEST_DATA_FOLDER = Path("tests/test_data/")

SCHEMA_PATH = TEST_DATA_FOLDER / "gapi_test_data.json"

MODEL_PATH = TEST_DATA_FOLDER / "gapi_test_data.py"

TEST_DATA_PATH = TEST_DATA_FOLDER / "gapi_test_data_input.json"

TEST_DATA: dict[str, MAIN_TYPE] = {
    "_datetime": "2000-01-01T00:00:00Z",
    "_date": "2000-01-01",
    "_time": "20:20:39",
    "_timedelta": "P3D",
    "_ipv4": "192.168.1.1",
    "_ipv6": "::1",
    "_uuid": "3e4666bf-d5e5-4aa7-b8ce-cefe41c7568a",
    "_int": 1,
    "_float": 1.0,
    "_str": "string",
    "_bool": True,
    "_list": [
        "2000-01-01T00:00:00Z",
    ],
    "_dict": {
        "key": "string",
    },
    "FieldNameThatIsLongWithMultipleLines": "string",
    "mixed_numbers": [1, 1.0],
}
