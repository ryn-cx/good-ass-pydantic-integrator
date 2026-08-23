<!-- TODO: This README is trash -->
# Good Ass Pydantic Integrator (GAPI)

GAPI is a python library that generates Pydantic v2 based models from raw JSON data (or
JSON schemas), lets you customize the result, and provides a client that validates
responses against those models.

## Features

- Build a JSON schema from one or many JSON samples and emit a Pydantic v2 model.
- Auto-detect strings that are really `datetime`, `date`, `time`, `timedelta`,
  `IPv4Address`, `IPv6Address`, `UUID`, etc.
- Customize generated models with field replacements, type replacements, custom
  `@field_serializer` methods, and extra imports.
- `GAPIClient` base class that validates responses against the generated model
  or its all-optional copy, and caches the raw input so responses dump back
  exactly as they came in. It only ever reads the saved samples; writing them is
  the caller's, and models are only written by an explicit `rebuild_model`.

## Installation

```bash
uv add git+https://github.com/ryn-cx/good-ass-pydantic-integrator
```

## Quick start

Generate a Pydantic model from a single JSON object:

```python
from good_ass_pydantic_integrator import GAPI

gapi = GAPI(class_name="User")
gapi.add_object_from_dict(
    {
        "id": "3e4666bf-d5e5-4aa7-b8ce-cefe41c7568a",
        "name": "Ada",
        "created_at": "2025-01-01T12:00:00Z",
        "tags": ["admin", "early-access"],
    }
)
print(gapi.get_strict_models_content())
```

Output:

```python
# ruff: noqa: D100, D101
from typing import TYPE_CHECKING

from pydantic import AwareDatetime, BaseModel, ConfigDict

if TYPE_CHECKING:
    from uuid import UUID


class User(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    created_at: AwareDatetime
    tags: list[str]
```

## Building models from data

`GAPI` accepts JSON data and JSON schemas from a dict, a string, a file, or a
folder of files. Every call merges into the same underlying schema, so you can
combine multiple sample responses to widen the resulting types.

```python
from pathlib import Path
from good_ass_pydantic_integrator import GAPI

gapi = GAPI(class_name="Response")

# Any combination of these works
gapi.add_object_from_dict({"value": 1})
gapi.add_object_from_string('{"value": "string"}')
gapi.add_object_from_file(Path("response.json"))
gapi.add_objects_from_folder(Path("responses/"))
gapi.add_schema_from_file(Path("json_schema.json"))

gapi.write_json_schema_to_file(Path("out/api_response.json"))
gapi.write_strict_models_to_file(Path("out/api_response.py"))
```

## Customizing generated models

Customizations are applied after `datamodel-code-generator` runs but before the
file is formatted, so you can rewrite fields, swap types, inject serializers, and
add imports.

### Replace the type annotation (and add a custom import)

```python
from good_ass_pydantic_integrator import GAPI
from good_ass_pydantic_integrator.customizer import GAPICustomizer

customizer = GAPICustomizer()
customizer.add_replacement_type(
    class_name="Model",
    field_name="status",
    new_type="Literal['active', 'inactive']",
)
customizer.add_additional_import("from typing import Literal")

gapi = GAPI(customizer=customizer)
gapi.add_object_from_dict({"status": "active"})
print(gapi.get_strict_models_content())
```

Output:

```python
# ruff: noqa: D100, D101
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "inactive"]
```
### Replace a whole field

`new_field` accepts either a full annotated assignment (`"count: int = ..."`) or
just the annotation portion (`"int = ..."`), in which case `field_name` is
prepended automatically.

```python
from good_ass_pydantic_integrator import GAPI
from good_ass_pydantic_integrator.customizer import GAPICustomizer

customizer = GAPICustomizer()
customizer.add_replacement_field(
    class_name="Model",
    field_name="total_count",
    new_field='int = Field(default=0, description="Number of items.")',
)

gapi = GAPI(customizer=customizer)
gapi.add_object_from_dict({"TotalCount": "1"})
print(gapi.get_strict_models_content())
```

Output:

```python
# ruff: noqa: D100, D101
from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_count: int = Field(default=0, description="Number of items.")
```


### Add a custom serializer

`add_custom_serializer` wraps your body in a `@field_serializer` method. The
`value` parameter is typed from the existing field annotation.

```python
from good_ass_pydantic_integrator import GAPI
from good_ass_pydantic_integrator.customizer import GAPICustomizer

customizer = GAPICustomizer()
customizer.add_custom_serializer(
    field_name="created_at",
    serializer_code='return value.isoformat().replace("+00:00", "Z")',
    output_type="str",
    class_name="User",
)

gapi = GAPI(class_name="User", customizer=customizer)
gapi.add_object_from_dict({"created_at": "2025-01-01T12:00:00Z"})
print(gapi.get_strict_models_content())
```

Output:

```python
# ruff: noqa: D100, D101, D102
from pydantic import AwareDatetime, BaseModel, ConfigDict, field_serializer


class User(BaseModel):
    model_config = ConfigDict(extra="forbid")
    created_at: AwareDatetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: AwareDatetime) -> str:
        return value.isoformat().replace("+00:00", "Z")
```


## `GAPIClient` - Generated models and the client that validates against them

`GAPIClient` is a generic base class for creating a Pydantic model that is
generated from the responses it has been given.

Every model is generated twice. `user_model.py` holds the model as the data
actually looked, with `extra="forbid"` and required fields; `user_model_optional.py`
holds the same classes with `extra="ignore"` and every field optional, for parsing
data that has drifted from the model. Which one `parse` uses is the `optional`
argument, and `parse_or_optional` tries the first and falls back to the second.

Models generated for a `GAPIClient` inherit from `GAPIBaseModel` (a `BaseModel`
subclass) instead of `pydantic.BaseModel`. `GAPIBaseModel` records the raw input it
was validated from and exposes it as `model.raw_input`, which is how
`dump_response` returns the untouched original response — pydantic itself does
not retain the raw input once a model is built.

A runnable example is available in the [`example/`](example/) directory:

| File                                             | Purpose                                                                                                                                  |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| [`example/user_model.py`](examples/user_model.py)   | The Pydantic response model. |
| [`example/user_client.py`](examples/user_client.py) | The `GAPIClient` subclass. Run it with `uv run python examples/user_client.py`. |


### `GAPIClient` operations

```python
# Validate a response. `parse` takes the downloaded text and reads it with
# `transform_input`, which is `json.loads` unless a subclass overrides it. Text
# the model no longer fits raises; nothing is written or regenerated here.
user = UserClient.parse(response)

# Validate against the all-optional copy of the model, skipping every check on
# which fields have to be there.
user = UserClient.parse(response, optional=True)

# Validate against the model, falling back to the all-optional copy. The
# fallback logs "Parse failed for <identifier>" and writes nothing, so that
# warning is the only record that the response drifted.
user = UserClient.parse_or_optional(response, "Users/1")

# Rewrite the all-optional copy from the current schema.
UserClient.write_optional_model()

# Return one or many models' raw input exactly as it was parsed. Only models
# produced by parse() can be dumped, and what comes back is the text itself.
UserClient.dump_response(user)
UserClient.dump_response([user, user])

# Rebuild the model and its all-optional copy from every saved sample. This is
# the only thing that writes a model, and it is run deliberately.
UserClient.rebuild_model()

# Reset the model file to a blank schema.
UserClient.write_blank_model()

# Prune saved samples that don't change the final schema.
UserClient.remove_redundant_json_files()
```
