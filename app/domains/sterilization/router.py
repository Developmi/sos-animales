"""Endpoints HTMX del dominio sterilization.

- GET /search — página completa de búsqueda (extiende base.html)
- GET /campaigns — fragmento HTMX con resultados según filtros
- GET /campaigns/{id} — vista detalle de una jornada
- GET /fixed-points — fragmento con puntos fijos por municipio

Delega toda la lógica a tools.py. Retorna fragmentos HTML para HTMX.
"""
