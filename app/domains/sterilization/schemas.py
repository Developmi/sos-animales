"""Pydantic schemas for Campaign and FixedPoint.

- CampaignCreate: validation for new campaign creation form.
- FixedPointCreate: validation for fixed sterilization point registration.
- CampaignFilter: query parameter filters for campaign searches.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional


class CampaignCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=3, max_length=255)
    municipality: str = Field(..., min_length=3, max_length=100)
    starts_at: datetime
    species: list[str]
    capacity: Optional[int] = Field(default=None, ge=1)
    is_free: bool = True
    requirements: Optional[str] = None
    booking_url: Optional[str] = None
    source_url: Optional[str] = None
    data_origin: str = "source_submitted"

    @field_validator("starts_at")
    @classmethod
    def validate_starts_at(cls, v: datetime) -> datetime:
        compare_val = v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
        if compare_val < datetime.now(timezone.utc):
            raise ValueError("La fecha de inicio no puede estar en el pasado")
        return v


class FixedPointCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=3, max_length=255)
    address: str = Field(..., min_length=5, max_length=500)
    municipality: str = Field(..., min_length=3, max_length=100)
    schedule_text: str = Field(..., min_length=3)
    species: list[str]
    is_free: bool = True
    requirements: Optional[str] = None
    source_url: Optional[str] = None
    data_origin: str = "source_submitted"


class CampaignFilter(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    municipality: str = "bogota"
    species: Optional[str] = None
