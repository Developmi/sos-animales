# SOS Animales

**Mapa nacional colaborativo de esterilización, perfiles de animales y verificación de fundaciones en Colombia.**

## Propósito

SOS Animales es una plataforma open data que conecta ciudadanos, fundaciones y veterinarios para:
- Localizar jornadas de esterilización y puntos fijos en todo Colombia.
- Dar visibilidad a animales en adopción con perfiles completos.
- Verificar fundaciones y refugios mediante un proceso de dos niveles.

**No gestiona dinero, no tiene cuentas de usuario, no tiene chat.** El core es 100% informacional.

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | FastAPI + SQLAlchemy async (asyncpg) |
| Base de datos | PostgreSQL (SOLO PostgreSQL, sin SQLite) |
| Frontend | HTMX + Pico.css + Jinja2 (sin build step JS) |
| Geocoding | Nominatim / OSM |
| Almacenamiento | Cloudflare R2 (fotos de animales) |
| Infraestructura | Bare metal con monitoreo (Uptime Kuma, Plausible, Grafana) |
| Correo | Google SMTP API (free tier, envío de PINs) |

## Estado del proyecto

**Fase 1 — MVP en desarrollo.** Ver [ROADMAP.md](ROADMAP.md) para alcance detallado v1.

## Cómo correr localmente

```bash
# Clonar
git clone https://github.com/tu-usuario/sos-animales.git
cd sos-animales

# Entorno virtual con uv
uv venv
source .venv/bin/activate

# Instalar dependencias
uv pip install -e .

# Variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# Inicializar base de datos
alembic upgrade head

# Ejecutar
uvicorn app.main:app --reload
```

## Arquitectura

Por dominios (`domains/`), cada uno con su propio `models.py`, `schemas.py`, `tools.py` y `router.py`:

| Dominio | Responsabilidad |
|---------|----------------|
| `sterilization` | Jornadas y puntos fijos de esterilización |
| `sources` | Fundaciones/refugios con estado pending/verified |
| `verification` | Proceso de verificación: requests, checklist, visits |
| `animals` | Perfiles de animales en adopción |
| `community` | Actualizaciones comunitarias con PIN + votación |

## Gobernanza del dato

- **Política de frescura**: 5 días sin confirmación → dato marcado como no confirmado (visible con advertencia).
- **Verificación de dos niveles**: presencial (radio ≤ 2h desde Bogotá) o remota (aliados virtuales), siempre con veterinario.
- **Conflicto comunidad vs. oficial**: se necesita un mínimo de votantes (configurable) para que la comunidad sobreescriba el estado oficial.
- **Sin gestión de dinero, cuentas de usuario, ni chat.**

## Licencia

**AGPL-3.0** — ver [LICENSE](LICENSE). Si alguien usa este código para un servicio web, debe publicar el código fuente de su versión modificada.

## Ver más

- [ROADMAP.md](ROADMAP.md) — alcance completo v1 y plan de fases.
- [CONTRIBUTING.md](CONTRIBUTING.md) — cómo contribuir.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — código de conducta.
- [SECURITY.md](SECURITY.md) — reportar vulnerabilidades.
