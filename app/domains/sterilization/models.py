"""Modelos SQLAlchemy del dominio sterilization.

- Campaign: jornada puntual de esterilización con fechas, especie(s),
  capacidad, requisitos y estado (scheduled/full/completed/cancelled).
- FixedPoint: punto fijo permanente (clínica, unidad móvil) con horario,
  especie(s), si es gratuito y requisitos.

Ambos modelos tienen last_confirmed_at para la política de frescura de 5 días.
"""
