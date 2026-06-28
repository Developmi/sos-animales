"""Endpoints HTMX del dominio animals.

- GET /animals/new — formulario de alta (solo fuentes).
- POST /animals — crear perfil.
- GET /animals — listado filtrado por municipio/especie/estado.
- GET /animals/{id} — detalle del perfil.
- POST /animals/{id}/adopt — marcar como adoptado (con PIN).

Delega toda la lógica a tools.py.
"""
