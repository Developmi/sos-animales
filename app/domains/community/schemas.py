"""Pydantic schemas for CommunityUpdate.

- CommunityUpdateCreate: validation for community reporting form.
  Requires XOR constraint between campaign_id and animal_id.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CommunityUpdateCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    update_type: str = Field(
        ...,
        pattern=r"^(confirmed|full|cancelled|wrong_info|adopted|in_treatment)$",
    )
    note: str | None = None
    campaign_id: int | None = None
    animal_id: int | None = None

    @model_validator(mode="after")
    def validate_single_target(self) -> "CommunityUpdateCreate":
        has_campaign = self.campaign_id is not None
        has_animal = self.animal_id is not None
        if not (has_campaign ^ has_animal):
            raise ValueError(
                "Debe especificar exactamente uno entre campaign_id o animal_id"
            )
        return self
