"""Modelo SQLAlchemy AnimalProfile.

- foto_url: str — URL pública en Cloudflare R2.
- especie: str — 'canino' | 'felino' (v1, solo estas dos).
- status: str — 'available' | 'adopted' | 'in_treatment'.
- is_sterilized: bool — para datos demográficos y análisis.
- source_id: FK a Source (puede ser verified o pending, con transparencia al usuario).

Un solo modelo unifica animales en adopción y su estado de esterilización.
"""
