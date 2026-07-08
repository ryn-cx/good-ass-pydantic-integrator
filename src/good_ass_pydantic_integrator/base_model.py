# TODO: Validate
"""Custom Pydantic base model that retains the input."""

from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, ValidationInfo, model_validator

if TYPE_CHECKING:
    from pydantic import ModelWrapValidatorHandler

    from good_ass_pydantic_integrator.constants import INPUT_TYPE

MODIFIER_CONTEXT_KEY = "gapi_modify"
"""Validation-context key holding an optional callable that transforms the raw
input before validation. A ``GAPIClient`` injects its ``modify_data`` hook here so
the model is built from the transformed shape while the raw input is preserved."""


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
        # A GAPIClient may pass a data modifier through the validation context.
        # Apply it once, at the root: pop it so nested models (validated inside
        # handler) don't re-apply it. The *original*, unmodified input is what we
        # record, so ``raw_input``/``dump`` still reflect exactly what was
        # downloaded even though the model is built from the transformed data.
        original = data
        context = info.context
        if isinstance(context, dict):
            modifier = context.pop(MODIFIER_CONTEXT_KEY, None)
            if modifier is not None:
                data = modifier(data)

        model = handler(data)
        object.__setattr__(model, "_gapi_raw_input", original)
        return model

    @property
    def raw_input(self) -> INPUT_TYPE:
        """The input used to create this model.

        Raises:
            ValueError: If the model was built via ``model_construct``, which
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
