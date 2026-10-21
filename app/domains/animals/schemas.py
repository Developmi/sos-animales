"""Pydantic schemas for AnimalProfile.

- AnimalCreate: validation of animal creation form.
- AnimalFilter: catalog search filter query parameters.
- AdoptAction: PIN validation payload to mark animal as adopted.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional

VALID_SPECIES = ["canino", "felino"]


class AnimalCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=100)
    species: str = Field(...)
    municipality: str = Field(..., min_length=3, max_length=100)
    breed: Optional[str] = None
    age_months: Optional[int] = Field(None, ge=1, le=360)
    age_years: Optional[int] = Field(None, ge=0, le=50)
    size: Optional[str] = Field(None, pattern=r"^(pequeno|mediano|grande)$")
    is_sterilized: bool = False
    description: Optional[str] = None
    sexo: Optional[str] = Field(None, pattern=r"^(macho|hembra)$")
    fecha_nacimiento: Optional[date] = None
    etapa_madurez: Optional[str] = Field(
        None, pattern=r"^(cachorro|joven|adulto|geronte)$"
    )
    condiciones_especiales: Optional[list[str]] = None
    compatible_ninos: Optional[bool] = None
    compatible_otros_animales: Optional[bool] = None
    microchip: Optional[str] = Field(None, max_length=50)
    source_url: Optional[str] = None
    data_origin: str = "source_submitted"

    @field_validator("fecha_nacimiento")
    @classmethod
    def validate_fecha_nacimiento(cls, v: date | None) -> date | None:
        if v and v > date.today():
            raise ValueError("La fecha de nacimiento no puede ser futura")
        return v

    @field_validator("species")
    @classmethod
    def validate_species(cls, v: str) -> str:
        if v not in VALID_SPECIES:
            raise ValueError(
                f"Especie inválida. Debe ser una de: {', '.join(VALID_SPECIES)}"
            )
        return v


class AnimalFilter(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    municipality: Optional[str] = None
    species: Optional[str] = Field(None, pattern=r"^(canino|felino)?$")


class AdoptAction(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
