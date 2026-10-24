"""Pydantic schemas for Campaign and FixedPoint.

- CampaignCreate: validation for new campaign creation form.
- FixedPointCreate: validation for fixed sterilization point registration.
- CampaignFilter: query parameter filters for campaign searches.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CampaignCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=3, max_length=255)
    municipality: str = Field(..., min_length=3, max_length=100)
    starts_at: datetime
    species: list[str]
    capacity: int | None = Field(default=None, ge=1)
    is_free: bool = True
    requirements: str | None = None
    booking_url: str | None = None
    source_url: str | None = None
    data_origin: str = "source_submitted"

    @field_validator("starts_at")
    @classmethod
    def validate_starts_at(cls, v: datetime) -> datetime:
        compare_val = v if v.tzinfo is not None else v.replace(tzinfo=UTC)
        if compare_val < datetime.now(UTC):
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
    requirements: str | None = None
    source_url: str | None = None
    data_origin: str = "source_submitted"


class CampaignFilter(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    municipality: str = "bogota"
    species: str | None = None
