"""Utilidades de geocoding vía Nominatim/OSM.

Convierte municipio + localidad (selects controlados, no campo libre)
a coordenadas lat/lng para el mapa Leaflet.

No se usa Google Maps ni servicios de pago. Cachea resultados para
evitar rate limiting de Nominatim.
"""
