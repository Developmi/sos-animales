# Contribuir a SOS Animales

## Cómo proponer una fuente nueva

1. Abre un issue con el nombre de la fundación/refugio.
2. Incluye dirección, contacto y redes sociales.
3. El equipo coordinará una verificación veterinaria.

## Cómo abrir un Pull Request

1. Asegúrate de que tu código pase `ruff check .`
2. Incluye tests para nueva funcionalidad.
3. Mantén los PRs enfocados (un cambio por PR).

## Estándares de código

- Linter: `ruff` (sin excepciones).
- Type hints en todo código nuevo.
- Docstrings en módulos y funciones públicas.
- Arquitectura por dominios (cada dominio con models/schemas/tools/router).
- Las `tools.py` solo contienen lógica pura (sin efectos secundarios).

## Alcance del proyecto

Este proyecto NO maneja:
- Donaciones o dinero.
- Cuentas de usuario individuales.
- Chat o mensajería.
- API de WhatsApp.

Si tu contribución toca alguno de estos temas, se rechazará.

## Licencia

Al contribuir aceptas que tu código se publique bajo AGPL-3.0.
