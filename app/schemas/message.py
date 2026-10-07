import datetime
from typing import Annotated

from pydantic import BaseModel, Field
from pydantic.functional_validators import AfterValidator

from app.domain.rider_id import normalize_rider_id


def _validate_rider_id(v: str) -> str:
    try:
        return normalize_rider_id(v)
    except Exception as e:
        raise ValueError(str(e)) from e


class MessageRequest(BaseModel):
    message_id: str = Field(..., min_length=1)
    rider_id: Annotated[str, AfterValidator(_validate_rider_id)]
    text: str = Field(..., min_length=1)
    received_at: datetime.datetime


class MessageResponse(BaseModel):
    reply: str
