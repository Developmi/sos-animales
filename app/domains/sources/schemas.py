"""Pydantic schemas for the sources domain.

- SourceRegisterIn: self-registration payload for shelters, organizations, and rescuers.
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional


class SourceRegisterIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=3, max_length=255)
    type: str = Field(..., pattern=r"^(official|verified_shelter|community)$")
    municipality: str = Field(..., min_length=3, max_length=100)
    department: str = Field(..., min_length=3, max_length=100)
    contact_email: Optional[EmailStr] = None
    contact_whatsapp: Optional[str] = None
    contact_url: Optional[str] = None
