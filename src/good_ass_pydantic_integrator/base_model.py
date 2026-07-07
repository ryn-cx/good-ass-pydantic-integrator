"""Custom Pydantic base model that retains the input."""

from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, model_validator

if TYPE_CHECKING:
    from pydantic import ModelWrapValidatorHandler

    from good_ass_pydantic_integrator.constants import INPUT_TYPE


class GAPIBaseModel(BaseModel):
    """Custom Pydantic base model that retains the input."""

    @model_validator(mode="wrap")
    @classmethod
    def _save_raw_input(
        cls,
        data: Any,  # noqa: ANN401 - Data can be anything.
        handler: ModelWrapValidatorHandler[Self],
    ) -> Self:
        model = handler(data)
        object.__setattr__(model, "_gapi_raw_input", data)
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
