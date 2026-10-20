"""Pydantic schemas for VerificationRequest, ChecklistResult, and Visit.

- VerificationRequestCreate: initiation of shelter verification process.
- ChecklistItem: single criterion evaluated during veterinary inspection visit.
- ChecklistSubmit: batch of criteria evaluated during a visit.
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


class VerificationRequestCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_id: int
    evidence: Optional[str] = Field(None, max_length=10000)


class ChecklistItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    criterion: str = Field(..., min_length=3, max_length=100)
    passed: bool
    notes: Optional[str] = None


class ChecklistSubmit(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    visit_id: int
    items: list[ChecklistItem] = Field(..., min_length=1)
