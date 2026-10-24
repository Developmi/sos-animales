"""Pydantic schemas for AnimalProfile.

- AnimalCreate: validation of animal creation form.
- AnimalFilter: catalog search filter query parameters.
- AdoptAction: PIN validation payload to mark animal as adopted.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_SPECIES = ["canino", "felino"]


class AnimalCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=100)
    species: str = Field(...)
    municipality: str = Field(..., min_length=3, max_length=100)
    breed: str | None = None
    age_months: int | None = Field(None, ge=1, le=360)
    age_years: int | None = Field(None, ge=0, le=50)
    size: str | None = Field(None, pattern=r"^(pequeno|mediano|grande)$")
    is_sterilized: bool = False
    description: str | None = None
    sexo: str | None = Field(None, pattern=r"^(macho|hembra)$")
    fecha_nacimiento: date | None = None
    etapa_madurez: str | None = Field(
        None, pattern=r"^(cachorro|joven|adulto|geronte)$"
    )
    condiciones_especiales: list[str] | None = None
    compatible_ninos: bool | None = None
    compatible_otros_animales: bool | None = None
    microchip: str | None = Field(None, max_length=50)
    source_url: str | None = None
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

    municipality: str | None = None
    species: str | None = Field(None, pattern=r"^(canino|felino)?$")


class AdoptAction(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
