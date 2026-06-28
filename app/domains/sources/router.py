"""Endpoints HTMX del dominio sources.

- GET /register — formulario de auto-registro (con aviso Ley 1581)
- POST /register — enviar formulario, crea source en pending
- GET /sources — directorio de fuentes por municipio
- GET /sources/{id} — perfil público con badge de estado

Delega toda la lógica a tools.py.
"""
