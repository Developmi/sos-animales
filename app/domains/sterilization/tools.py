"""Funciones puras de negocio del dominio sterilization.

- find_nearby_campaigns: busca jornadas por municipio, especie y estado.
- search_by_filters: búsqueda combinada con múltiples criterios.
- get_campaign_detail: devuelve datos completos de una jornada.
- get_fixed_points_by_municipality: puntos fijos activos en un municipio.

Sin dependencia de FastAPI (Request, Response). Solo reciben db session + parámetros.
"""
