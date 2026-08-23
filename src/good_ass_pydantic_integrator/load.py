# TODO: Validate
"""Read a downloaded file into the model it fits."""

import logging

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


# TODO: Validate
def _validate[T: BaseModel](model: type[T], data: str | bytes | object) -> T:
    """Read `data` with `model`, parsing it as JSON when it is text."""
    if isinstance(data, str | bytes):
        return model.model_validate_json(data)
    return model.model_validate(data)


# TODO: Validate
def model_validate_json[T: BaseModel](
    strict_model: type[T],
    optional_model: type[T],
    data: str | bytes | object,
    log_id: str,
) -> T:
    """Read a downloaded file, falling back to the all-optional model.

    The strict model is tried first. When the file no longer fits it the failure
    is logged and the all-optional model is used, so a response that has drifted
    still parses.

    Args:
        strict_model: The model as the recordings describe it.
        optional_model: The same model with every field optional.
        data: The downloaded file, as JSON text or as an already parsed object.
        log_id: Identifies the file in the log when the strict model does not fit.

    Returns:
        The model the file was read into.
    """
    try:
        return _validate(strict_model, data)
    except ValidationError:
        logger.warning("Parse failed for %s", log_id)
        logger.debug("Parse failure detail for %s", log_id, exc_info=True)
        return _validate(optional_model, data)
