"""Endpoints HTMX del dominio community.

- GET /community/update — formulario de reporte (requiere PIN).
- POST /community/update — enviar reporte comunitario.
- GET /community/votes/{update_id} — estado de votación.
- POST /community/vote — registrar voto.

Delega toda la lógica a tools.py.
"""
