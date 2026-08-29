# TODO: Validate
"""Good Ass Pydantic Integrator."""

import logging

from good_ass_pydantic_integrator.base_model import GAPIBaseModel as GAPIBaseModel
from good_ass_pydantic_integrator.customizer import CustomSerializer as CustomSerializer
from good_ass_pydantic_integrator.customizer import GAPICustomizer as GAPICustomizer
from good_ass_pydantic_integrator.customizer import ReplacementField as ReplacementField
from good_ass_pydantic_integrator.customizer import ReplacementType as ReplacementType
from good_ass_pydantic_integrator.gapi import GAPI as GAPI
from good_ass_pydantic_integrator.generate import (
    generate_model as generate_model,
)
from good_ass_pydantic_integrator.generate import (
    recorded_model_names as recorded_model_names,
)
from good_ass_pydantic_integrator.generate import (
    redundant_recordings as redundant_recordings,
)
from good_ass_pydantic_integrator.load import (
    model_validate_json as model_validate_json,
)

logging.getLogger(__name__).addHandler(logging.NullHandler())
