# TODO: Validate
"""Custom Pydantic base model that retains the input."""

from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, ValidationInfo, model_validator

if TYPE_CHECKING:
    from pydantic import ModelWrapValidatorHandler

    from good_ass_pydantic_integrator.constants import JSON_VALUE

RAW_INPUT_CONTEXT_KEY = "gapi_raw_input"
"""Validation-context key holding what the caller handed the client, before it
was read into the shape pydantic validates. A caller puts the downloaded text
here so the root model records that rather than the parsed structure."""


class GAPIBaseModel(BaseModel):
    """Custom Pydantic base model that retains the input."""

    @model_validator(mode="wrap")
    @classmethod
    def _save_raw_input(
        cls,
        data: Any,  # noqa: ANN401 - Data can be anything.
        handler: ModelWrapValidatorHandler[Self],
        info: ValidationInfo,
    ) -> Self:
        # A caller passes what it was handed through the validation context.
        # It is popped so only the root model records it and the models nested
        # inside (validated inside handler) record the part of the parsed
        # structure they were built from.
        original = data
        context = info.context
        if isinstance(context, dict):
            given = context.pop(RAW_INPUT_CONTEXT_KEY, None)
            if given is not None:
                original = given

        model = handler(data)
        object.__setattr__(model, "_gapi_raw_input", original)
        return model

    @property
    def raw_input(self) -> JSON_VALUE:
        """The input used to create this model.

        For a model validated with the raw input in its context, this is the
        text the caller was handed. For a model nested inside one, it is the
        part of the parsed structure that model was built from.

        Raises:
            ValueError: If the model was built via `model_construct`, which
                bypasses validation and so records no raw input.
        """
        try:
            return self.__dict__["_gapi_raw_input"]
        except KeyError:
            msg = (
                f"{type(self).__name__} has no raw input; it was built without "
                "validation (via model_construct)."
            )
            raise ValueError(msg) from None
