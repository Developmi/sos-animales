# Roadmap — SOS Animales

> ⚠️ **Para cualquier persona que lea esto**: este roadmap está diseñado para que un desarrollador junior pueda entender QUÉ hay que construir, EN QUÉ ORDEN y CUÁNDO está "terminado" cada módulo. Si algo no se entiende, es porque falta claridad — no porque "es obvio".

---

## 📌 Filosofía del proyecto

SOS Animales es una plataforma **open data** (datos abiertos) que centraliza tres cosas en un solo mapa:

1. **Jornadas de esterilización** gratuitas o de bajo costo en Colombia.
2. **Perfiles de animales** en adopción con foto y datos.
3. **Fundaciones/refugios verificados** (con un proceso riguroso).

**Lo que NO es SOS Animales:**
- ❌ No maneja dinero (no donaciones, no pagos, no intermediación económica).
- ❌ No tiene cuentas de usuario (no login, no registro de personas).
- ❌ No tiene chat ni mensajería.
- ❌ No tiene WhatsApp API.

**El core es 100% informacional:** mostrar datos útiles y confiables, nada más.

---

## 🧱 Stack técnico

| Capa | Tecnología | Por qué |
|------|-----------|---------|
| Backend | FastAPI + Python | Velocidad de desarrollo, Pydantic para validación automática |
| Base de datos | PostgreSQL | Relacional, maduro, suficiente para este volumen |
| Driver DB | asyncpg | Conexión asíncrona a PostgreSQL (rendimiento) |
| ORM | SQLAlchemy 2.0 (async) | Mapeo object-relacional, migrations con Alembic |
| Frontend | HTMX + Pico.css | Sin build step, sin JavaScript framework, carga en <1s |
| Templates | Jinja2 | Motor de plantillas HTML (integradas en FastAPI) |
| Mapas | Leaflet + OpenStreetMap | Gratuito, sin API key, sin Google Maps |
| Geocoding | Nominatim (OSM) | Convierte dirección → coordenadas, gratuito |
| Fotos | Cloudflare R2 (free tier) | Almacenamiento externo, URLs públicas, 10 GB gratis |
| Correo | Google SMTP API | Envío de PINs (free tier, 100 emails/día) |
| Analytics | Plausible | Privacidad, sin cookies de terceros, opt-in obligatorio |
| Monitoreo | Uptime Kuma + Grafana | El creador ya tiene esta infraestructura |
| Infraestructura | Bare metal del creador | VPS personal con backups a R2 + S3 |

---

## 🗺️ Fase 1 — MVP (estamos aquí)

### ¿Qué significa "MVP"?

MVP = **Minimum Viable Product**. Es la versión más pequeña que sigue siendo útil. No busca ser perfecto, busca **validar que la idea funciona**. Todo lo que no es esencial para esa validación se deja para después.

### Criterio de "Hecho" del MVP

El MVP está completo cuando:
1. Una persona puede entrar al sitio, buscar jornadas de esterilización en su municipio y ver resultados en un mapa.
2. Una fundación puede registrarse (aunque quede en `pending`).
3. Una persona puede ver perfiles de animales en adopción con foto.
4. La comunidad puede reportar actualizaciones (confirmar, cancelar, corregir) usando un PIN.
5. El creador (o un voluntario veterinario) puede registrar el resultado de una visita de verificación.

---

## 📋 Fase 1 — Lista completa de tareas

Cada tarea tiene: **archivos involucrados**, **criterio de "hecho"**, y **dependencias** (qué tiene que estar listo antes).

---

### 🔵 Pilar 0: Infraestructura base (hacerlo primero, todo depende de esto)

#### 0.1 — Configurar pyproject.toml y entorno

| Campo | Detalle |
|-------|---------|
| **Qué** | Tener el archivo `pyproject.toml` con todas las dependencias y el entorno virtual funcionando. |
| **Archivos** | `pyproject.toml`, `.env.example` |
| **Dependencias** | Ninguna (es lo primero) |
| **Hecho cuando** | `uv run python -c "import fastapi; import sqlalchemy; import asyncpg; print('ok')"` no da error |

**Dependencias del proyecto:**
```
fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic,
pydantic-settings, jinja2, python-multipart, passlib[bcrypt],
httpx, python-dotenv
```

**Dependencias de desarrollo:**
```
pytest, pytest-asyncio, ruff
```

---

#### 0.2 — Configurar base de datos (PostgreSQL)

| Campo | Detalle |
|-------|---------|
| **Qué** | Tener PostgreSQL corriendo, con una base de datos creada y accesible desde la app. |
| **Archivos** | `app/database.py`, `app/config.py`, `.env` |
| **Dependencias** | 0.1 |
| **Hecho cuando** | La app puede conectarse a PostgreSQL usando la URL en `DATABASE_URL` |

**.env necesario:**
```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/sos_animales
```

**Código necesario en `app/database.py`:**
- Crear el engine asíncrono con `create_async_engine(DATABASE_URL)`.
- Crear `async_session = sessionmaker(engine, class_=AsyncSession)`.
- Crear `Base = declarative_base()`.
- Función `get_db()` que sea un `async generator` que dé una sesión y la cierre al terminar.

**Código necesario en `app/config.py`:**
- Clase `Settings(BaseSettings)` con `DATABASE_URL: str` y las demás variables.
- Usar `model_config = SettingsConfigDict(env_file=".env")`.

---

#### 0.3 — Configurar Alembic

| Campo | Detalle |
|-------|---------|
| **Qué** | Tener Alembic configurado para generar y aplicar migraciones. |
| **Archivos** | `alembic.ini`, `migrations/`, `app/database.py` |
| **Dependencias** | 0.2 |
| **Hecho cuando** | `alembic revision --autogenerate -m "init"` y `alembic upgrade head` funcionan sin error |

**Pasos:**
```bash
alembic init migrations
```
Editar `migrations/env.py` para que use la Base declarativa de `app.database` y la URL del `.env`.

---

#### 0.4 — Configurar StaticFiles y templates base

| Campo | Detalle |
|-------|---------|
| **Qué** | FastAPI sirve archivos estáticos y se puede renderizar HTML con Jinja2. |
| **Archivos** | `app/main.py`, `app/shared/templates/base.html` |
| **Dependencias** | 0.1 |
| **Hecho cuando** | Entrar a `http://localhost:8000/` devuelve el HTML de `base.html` |

**Código necesario en `app/main.py`:**
- Crear la app FastAPI.
- Configurar `Jinja2Templates(directory="app/shared/templates")`.
- Montar `StaticFiles(directory="app/static")` en `/static`.
- Incluir los routers de cada dominio (al principio vacíos).

**Código necesario en `base.html`:**
- `<head>` con charset, viewport, title block.
- Script de HTMX desde CDN (`https://unpkg.com/htmx.org`).
- CSS de Pico.css desde CDN.
- `{% block content %}{% endblock %}` para que cada página extienda.
- `{% include "nav.html" %}` y `{% include "footer.html" %}`.

---

### 🩵 Pilar 1: Sources (segundo — necesario para que existan las fuentes de datos)

#### 1.1 — Modelo Source

| Campo | Detalle |
|-------|---------|
| **Qué** | Tabla `sources` en PostgreSQL con los campos necesarios. |
| **Archivos** | `app/domains/sources/models.py`, migración de Alembic |
| **Dependencias** | 0.3 |
| **Hecho cuando** | `alembic upgrade head` crea la tabla `sources` |

**Campos del modelo `Source`:**
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK, autoincrement | Identificador único |
| `name` | String(255), NOT NULL | Nombre de la fundación/refugio |
| `type` | String(50), NOT NULL | `official`, `verified_shelter`, `community` |
| `status` | String(20), NOT NULL, default `pending` | `pending` o `verified` |
| `municipality` | String(100), NOT NULL | Municipio (select controlado, no campo libre) |
| `department` | String(100), NOT NULL | Departamento (select controlado) |
| `contact_email` | String(255) | Correo de contacto (se usa para enviar PINs) |
| `contact_whatsapp` | String(50) | WhatsApp de contacto |
| `contact_url` | String(500) | Sitio web o redes sociales |
| `verified_at` | DateTime, nullable | Cuándo se verificó (null si sigue pending) |
| `is_active` | Boolean, default `true` | Si la fuente está activa |
| `created_at` | DateTime, default `now()` | Fecha de registro |

---

#### 1.2 — Formulario de auto-registro de Source

| Campo | Detalle |
|-------|---------|
| **Qué** | Una fundación puede llenar un formulario para registrarse (queda en `pending`). |
| **Archivos** | `app/domains/sources/router.py`, `app/domains/sources/tools.py`, `app/domains/sources/templates/register_form.html` |
| **Dependencias** | 1.1 |
| **Hecho cuando** | Al enviar el formulario, se crea un registro en `sources` con `status='pending'` |

**Reglas de negocio:**
- Si la fuente se registra, su estado inicial siempre es `pending`.
- Mientras está `pending`, los usuarios ven un badge amarillo "No verificada — verifica antes de confiar".
- El formulario debe incluir el aviso de tratamiento de datos (Ley 1581).

---

#### 1.3 — Perfil público de Source

| Campo | Detalle |
|-------|---------|
| **Qué** | Cada fuente tiene una página pública con su información y badge de estado. |
| **Archivos** | `app/domains/sources/templates/source_profile.html`, `tools.py` |
| **Dependencias** | 1.1 |
| **Hecho cuando** | `GET /sources/{id}` muestra el perfil con badge `pending` o `verified` |

**Layout:**
- Nombre de la fuente.
- Badge de estado (rojo/amarillo para `pending`, verde para `verified`).
- Datos de contacto.
- Lista de sus campañas activas.
- Lista de sus animales en adopción.

---

### 💚 Pilar 2: Sterilization (tercero — el core del proyecto)

#### 2.1 — Modelos Campaign y FixedPoint

| Campo | Detalle |
|-------|---------|
| **Qué** | Tablas `campaigns` y `fixed_points` en PostgreSQL. |
| **Archivos** | `app/domains/sterilization/models.py`, migración Alembic |
| **Dependencias** | 0.3, 1.1 |
| **Hecho cuando** | `alembic upgrade head` crea ambas tablas |

**Modelo `Campaign`:**
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | |
| `source_id` | FK → sources.id | Quién publica esta jornada |
| `title` | String(255) | Nombre de la jornada |
| `municipality` | String(100), NOT NULL | Municipio (select) |
| `lat` | Float | Coordenada (de Nominatim) |
| `lng` | Float | Coordenada (de Nominatim) |
| `starts_at` | DateTime, NOT NULL | Cuándo empieza |
| `ends_at` | DateTime, nullable | Cuándo termina |
| `species` | ARRAY(String) | `['canino']`, `['felino']`, o `['canino','felino']` |
| `capacity` | Integer, nullable | Cupos totales (si se conoce) |
| `is_free` | Boolean, default `true` | ¿Es gratuito? |
| `booking_url` | Text, nullable | Link para agendar cita |
| `requirements` | Text, nullable | Requisitos en texto |
| `status` | String(20), default `scheduled` | `scheduled`, `full`, `completed`, `cancelled` |
| `last_confirmed_at` | DateTime, nullable | Última confirmación (política de 5 días) |
| `created_at` | DateTime, default `now()` | |

**Modelo `FixedPoint`:**
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | |
| `source_id` | FK → sources.id | |
| `name` | String(255) | Nombre del punto fijo |
| `address` | String(500) | Dirección |
| `lat` | Float | |
| `lng` | Float | |
| `municipality` | String(100) | |
| `schedule_text` | Text | "Miércoles cada 15 días, 8am-12pm" |
| `species` | ARRAY(String) | |
| `is_free` | Boolean, default `true` | |
| `requirements` | Text | |
| `last_confirmed_at` | DateTime, nullable | |
| `created_at` | DateTime, default `now()` | |

---

#### 2.2 — Funciones de búsqueda de campañas

| Campo | Detalle |
|-------|---------|
| **Qué** | Funciones para buscar y filtrar jornadas en `tools.py`. |
| **Archivos** | `app/domains/sterilization/tools.py` |
| **Dependencias** | 2.1 |
| **Hecho cuando** | Llamar a `find_nearby_campaigns(db, "bogota", ["canino"])` devuelve campañas de Bogotá para perros |

**Funciones a implementar:**
- `find_nearby_campaigns(db, municipality, species=None, only_active=True)` → lista de Campaign.
- `get_campaign_detail(db, campaign_id)` → Campaign con datos de la fuente.
- `get_fixed_points_by_municipality(db, municipality)` → lista de FixedPoint.

**Reglas:**
- Si `only_active=True`, filtrar donde `status = 'scheduled'` y `starts_at >= hoy`.
- Si pasó el umbral de 5 días desde `last_confirmed_at`, la campaña se muestra con advertencia visual.

---

#### 2.3 — Página de búsqueda y resultados

| Campo | Detalle |
|-------|---------|
| **Qué** | Página con selector de municipio/especie y un div que se llena con resultados vía HTMX. |
| **Archivos** | `app/domains/sterilization/router.py`, `app/domains/sterilization/templates/index.html`, `map_results.html` |
| **Dependencias** | 2.2 |
| **Hecho cuando** | Cambiar el select de municipio actualiza los resultados sin recargar la página |

**Flujo HTMX:**
1. `index.html` carga con selects de municipio y especie.
2. Al cambiar el select → `hx-get="/campaigns?municipality=..." hx-target="#results"`.
3. El endpoint GET /campaigns llama a `find_nearby_campaigns()` y devuelve `map_results.html` (solo el fragmento, no la página completa).
4. HTMX inyecta ese HTML en `<div id="results">`.

**Consideraciones:**
- Los municipios deben ser un `<select>` con opciones fijas (no campo libre). Sugerencia: usar datos abiertos de la DIVIPOLA (códigos de municipios de Colombia) como seed.
- Si no hay resultados, mostrar "No encontramos jornadas en este municipio. ¿Conoces alguna? [Reportar]" (esto alimenta el engagement comunitario).

---

#### 2.4 — Mapa Leaflet con pines

| Campo | Detalle |
|-------|---------|
| **Qué** | En la página de resultados se ve un mapa con pines en las ubicaciones de las jornadas. |
| **Archivos** | `app/domains/sterilization/templates/index.html` (sección del mapa), `app/domains/sterilization/templates/map_results.html` (datos para pines) |
| **Dependencias** | 2.3 |
| **Hecho cuando** | Los resultados se ven como una lista + pines en el mapa |

**Cómo funciona:**
- `map_results.html` incluye un `<script>` pequeño que lee los `data-lat` y `data-lng` de cada resultado y los pinta como pines en Leaflet.
- No necesita build step: Leaflet CSS y JS se cargan desde CDN.
- Cada pin tiene un popup con el nombre de la jornada y un enlace al detalle.

---

#### 2.5 — Detalle de campaña y tarjeta de punto fijo

| Campo | Detalle |
|-------|---------|
| **Qué** | Al hacer clic en una jornada, se ve su página de detalle completo. |
| **Archivos** | `campaign_detail.html`, `campaign_card.html`, `fixed_point_card.html` |
| **Dependencias** | 2.3 |
| **Hecho cuando** | `GET /campaigns/{id}` muestra datos completos + mapa con la ubicación |

---

### 💛 Pilar 3: Animals (cuarto — dar visibilidad a los animales)

#### 3.1 — Modelo AnimalProfile

| Campo | Detalle |
|-------|---------|
| **Qué** | Tabla `animal_profiles` en PostgreSQL. |
| **Archivos** | `app/domains/animals/models.py`, migración Alembic |
| **Dependencias** | 0.3, 1.1 |
| **Hecho cuando** | `alembic upgrade head` crea la tabla |

**Campos:**
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | |
| `source_id` | FK → sources.id | Fuente que publica (verified o pending) |
| `name` | String(100) | Nombre del animal |
| `species` | String(20), NOT NULL | `canino` o `felino` (v1 solo estos dos) |
| `breed` | String(100), nullable | Raza aproximada |
| `age_years` | Integer, nullable | Edad aproximada |
| `size` | String(20), nullable | `pequeno`, `mediano`, `grande` |
| `foto_url` | String(500) | URL pública en Cloudflare R2 |
| `status` | String(20), default `available` | `available`, `adopted`, `in_treatment` |
| `is_sterilized` | Boolean, default `false` | ¿Está esterilizado? |
| `description` | Text, nullable | Descripción libre |
| `municipality` | String(100) | Municipio donde está |
| `created_at` | DateTime | |
| `adopted_at` | DateTime, nullable | Cuándo se adoptó |

---

#### 3.2 — Formulario de alta de animal

| Campo | Detalle |
|-------|---------|
| **Qué** | Una fuente (verified o pending) puede subir un perfil de animal con foto. |
| **Archivos** | `app/domains/animals/router.py`, `app/domains/animals/tools.py`, `profile_form.html` |
| **Dependencias** | 3.1 |
| **Hecho cuando** | Al enviar el formulario con foto, se crea el perfil y la foto se sube a R2 |

**Upload de foto:**
- La foto se recibe como `multipart/form-data`.
- Se sube a R2 usando la library `boto3` (o `aioboto3` para async) configurada con las credenciales R2.
- La URL pública se guarda en `foto_url`.
- Tamaño máximo sugerido: 2MB por foto.

**Transparencia:**
- Si la fuente es `pending`, la página del perfil muestra: "Esta fuente no está verificada — contactar bajo tu propia responsabilidad."
- Si la fuente es `verified`, se muestra un badge verde.

---

#### 3.3 — Listado y detalle de animales

| Campo | Detalle |
|-------|---------|
| **Qué** | Página con filtros por municipio/especie/estado que muestra tarjetas de animales. |
| **Archivos** | `profile_list.html`, `profile_card.html`, `profile_detail.html` |
| **Dependencias** | 3.2 |
| **Hecho cuando** | Se puede navegar por animales, filtrar y ver detalle completo |

**Vistas:**
- `profile_list.html`: fragmento HTMX que se recarga al cambiar filtros.
- `profile_card.html`: tarjeta individual con foto miniatura, nombre, especie, estado, badge de esterilización.
- `profile_detail.html`: página completa con foto grande, datos, descripción, info de la fuente.

---

#### 3.4 — Marcar como adoptado

| Campo | Detalle |
|-------|---------|
| **Qué** | La fuente puede marcar un animal como adoptado usando el PIN. |
| **Archivos** | `app/domains/animals/tools.py`, router |
| **Dependencias** | 3.1, 5.2 (PIN) |
| **Hecho cuando** | Enviar el PIN correcto cambia `status` de `available` a `adopted` |

---

### 🩷 Pilar 4: Community (quinto — mantener los datos actualizados)

#### 4.1 — Modelo CommunityUpdate

| Campo | Detalle |
|-------|---------|
| **Qué** | Tabla `community_updates` en PostgreSQL. |
| **Archivos** | `app/domains/community/models.py`, migración Alembic |
| **Dependencias** | 0.3, 2.1, 3.1 |
| **Hecho cuando** | `alembic upgrade head` crea la tabla |

**Campos:**
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | |
| `campaign_id` | FK → campaigns.id, nullable | A qué jornada se refiere (null si es sobre animal) |
| `animal_id` | FK → animal_profiles.id, nullable | A qué animal se refiere (null si es sobre jornada) |
| `pin_hash` | String(255) | Hash bcrypt del PIN de 4 dígitos |
| `update_type` | String(30) | `confirmed`, `full`, `cancelled`, `wrong_info` |
| `note` | Text, nullable | Explicación libre |
| `votes` | Integer, default `0` | Votos de la comunidad |
| `created_at` | DateTime, default `now()` | |

**Restricción**: una actualización debe referirse a campaign_id O animal_id (no ambos, no ninguno).

---

#### 4.2 — Sistema de PIN (generación y envío)

| Campo | Detalle |
|-------|---------|
| **Qué** | Cuando se crea una campaña o perfil de animal, el sistema genera un PIN de 4 dígitos y lo envía por correo. |
| **Archivos** | `app/domains/community/tools.py`, `app/shared/security.py` |
| **Dependencias** | 0.2 (SMTP config), 4.1 |
| **Hecho cuando** | Crear una campaña genera un PIN y se envía un correo a la dirección de la fuente |

**Flujo:**
1. El source crea una campaña (o perfil de animal) e ingresa su correo electrónico.
2. El sistema llama a `generate_pin()`:
   - Usa `secrets.randbelow(9000) + 1000` para generar un número de 4 dígitos.
   - Hashea el PIN con `passlib.hash.bcrypt` y guarda el hash en la tabla correspondiente.
   - El PIN en texto plano SOLO se usa para enviarlo por correo, NUNCA se guarda en DB.
3. Se envía un email al source con: "Tu PIN para gestionar [campaña/perfil] es: 4821".
4. El source puede usar ese PIN para:
   - Reportar una actualización (ej: "la jornada se canceló").
   - Marcar un animal como adoptado.
   - Confirmar que los datos siguen vigentes.

**Seguridad:**
- El PIN tiene 4 dígitos → 10,000 combinaciones posibles.
- Rate limiting: máximo 3 intentos de PIN por hora (por campaign_id o animal_id).
- Después de 3 intentos fallidos, el PIN se invalida y se genera uno nuevo (enviado por correo).

---

#### 4.3 — Formulario de reporte comunitario

| Campo | Detalle |
|-------|---------|
| **Qué** | Cualquier persona puede reportar una actualización (confirmar, cancelar, reportar error). |
| **Archivos** | `update_form.html`, `update_confirmation.html`, `app/domains/community/router.py`, `tools.py` |
| **Dependencias** | 4.2 |
| **Hecho cuando** | Enviar un PIN válido crea un `CommunityUpdate` |

**Campos del formulario:**
- PIN (input de 4 dígitos).
- Tipo de update: select con opciones (`confirmed`, `full`, `cancelled`, `wrong_info`).
- Nota (textarea opcional).
- Botón "Reportar".

---

#### 4.4 — Votación comunitaria

| Campo | Detalle |
|-------|---------|
| **Qué** | Los miembros de la comunidad pueden votar para confirmar o refutar una actualización. |
| **Archivos** | `vote_status.html`, `app/domains/community/tools.py` |
| **Dependencias** | 4.3 |
| **Hecho cuando** | Una actualización con suficientes votos (≥ COMMUNITY_VOTE_THRESHOLD) cambia el estado oficial |

**Reglas:**
- El umbral se lee de `settings.COMMUNITY_VOTE_THRESHOLD` (default: 5, configurable en `.env`).
- Si se alcanza el umbral, el estado de la campaña/animal se actualiza al reportado por la comunidad.
- Si no se alcanza, prevalece el estado de la fuente oficial.
- **Rate limiting**: máximo 1 voto por IP cada 5 minutos para evitar manipulación.

---

### 🤍 Pilar 5: Verification (transversal — se usa cuando una fuente quiere ser verificada)

#### 5.1 — Modelos de verificación

| Campo | Detalle |
|-------|---------|
| **Qué** | Tablas `verification_requests`, `checklist_results`, `visits`. |
| **Archivos** | `app/domains/verification/models.py`, migración Alembic |
| **Dependencias** | 0.3, 1.1 |
| **Hecho cuando** | `alembic upgrade head` crea las tres tablas |

**Modelo `VerificationRequest`:**
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | |
| `source_id` | FK → sources.id | Source que solicita verificación |
| `status` | String(20), default `pending` | `pending`, `scheduled`, `done`, `rejected` |
| `submitted_evidence` | Text | Evidencia enviada por la fuente (fotos, documentos) |
| `reviewed_at` | DateTime, nullable | Cuándo se revisó |
| `created_at` | DateTime | |

**Modelo `Visit`:**
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | |
| `verification_request_id` | FK | |
| `visit_type` | String(20) | `presencial` o `remota` |
| `scheduled_at` | DateTime | Cuándo se agenda la visita |
| `completed_at` | DateTime, nullable | Cuándo se realizó |
| `visitor_name` | String(100) | Quién hizo la visita |
| `notes` | Text | Notas del visitante |

**Modelo `ChecklistResult`:**
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | |
| `visit_id` | FK → visits.id | |
| `criterion` | String(100) | Nombre del criterio evaluado |
| `passed` | Boolean | ¿Cumple? |
| `notes` | Text | Observaciones |

---

#### 5.2 — Formulario de checklist (solo admin/voluntarios)

| Campo | Detalle |
|-------|---------|
| **Qué** | Formulario para que el veterinario registre el resultado de la visita. |
| **Archivos** | `checklist_form.html`, `app/domains/verification/router.py`, `tools.py` |
| **Dependencias** | 5.1 |
| **Hecho cuando** | Al enviar el checklist, la fuente pasa a `verified` o se rechaza con motivos |

**Flujo:**
1. El admin (o voluntario veterinario) agenda una visita → `Visit` con `status = scheduled`.
2. Realiza la visita (presencial o remota) y llena el checklist.
3. Si TODOS los criterios pasan → `VerificationRequest.status = 'done'` y `Source.status = 'verified'`.
4. Si ALGUNO falla → se documenta qué falló y se puede reprogramar.

---

### 🧩 Pilar 6: Shared — código compartido

#### 6.1 — Utilidades de geocoding

| Campo | Detalle |
|-------|---------|
| **Qué** | Función que convierte municipio + localidad a coordenadas usando Nominatim. |
| **Archivos** | `app/shared/geo.py` |
| **Dependencias** | Ninguna |
| **Hecho cuando** | `geocode("bogota", "usaquen")` devuelve `(4.711, -74.032)` |

**Implementación:**
- Usar `httpx` para llamar a `https://nominatim.openstreetmap.org/search`.
- Cachear resultados para evitar rate limiting (al menos en memoria).
- Si Nominatim no responde, devolver `(None, None)` y mostrar mapa sin coordenadas.

---

#### 6.2 — Utilidades de seguridad

| Campo | Detalle |
|-------|---------|
| **Qué** | Funciones de generación de PIN, hashing y rate limiting. |
| **Archivos** | `app/shared/security.py` |
| **Dependencias** | Ninguna |
| **Hecho cuando** | `hash_pin("4821")` devuelve un hash bcrypt, `verify_pin("4821", hash)` devuelve `True` |

**Funciones:**
- `generate_pin() → str`: `secrets.randbelow(9000) + 1000`.
- `hash_pin(pin: str) → str`: `bcrypt.hash(pin)`.
- `verify_pin(pin: str, hash: str) → bool`: `bcrypt.verify(pin, hash)`.
- `check_rate_limit(key: str, max_attempts: int, window_seconds: int) → bool`: verifica si una IP o campaign_id excedió el límite.

---

### ⚖️ Pilar 7: Legal y compliance

#### 7.1 — Avisos de privacidad

| Campo | Detalle |
|-------|---------|
| **Qué** | Texto legal en cada formulario que recolecta datos personales. |
| **Archivos** | `app/shared/templates/privacy_notice.html` y los legales en `legal/` |
| **Dependencias** | Ninguna |
| **Hecho cuando** | Cada formulario tiene el aviso "Al enviar aceptas el tratamiento de datos según Ley 1581" |

**Archivos necesarios:**
- `privacy_notice.html` — snippet incluido en cada formulario.
- `legal/privacy_policy.html` — política completa.
- `legal/cookies_policy.html` — política de cookies.
- `legal/terms_of_use.html` — términos de uso.
- `legal/cookie_consent_banner.html` — banner de cookies con opt-in para Plausible.
- `legal/data_processing_consent.html` — consentimiento explícito para tratamiento.

---

### 📐 Pilar 8: Documentación del proyecto

| Archivo | Contenido | Hecho |
|---------|-----------|-------|
| `README.md` | Descripción, stack, cómo correr, gobernanza | ✅ |
| `ROADMAP.md` | Este archivo — alcance detallado | ✅ (en desarrollo) |
| `LICENSE` | Texto completo de AGPL-3.0 | ✅ |
| `CODE_OF_CONDUCT.md` | Código de conducta (Contributor Covenant) | ✅ |
| `CONTRIBUTING.md` | Cómo contribuir, estándares de código | ✅ |
| `SECURITY.md` | Cómo reportar vulnerabilidades | ✅ |
| `CHECKLIST_VETERINARIO.md` | Criterios concretos para visita veterinaria | 🔲 (lo crea el dueño) |

---

## 📐 Orden de implementación sugerido

```
Semana 1:
  └── 0.1 → 0.2 → 0.3 → 0.4 (infraestructura)
  └── 1.1 → 1.2 (sources base)
  └── 2.1 (modelos de esterilización)

Semana 2:
  └── 2.2 → 2.3 → 2.4 → 2.5 (búsqueda, mapa, detalle)
  └── 3.1 → 3.2 → 3.3 (animales)

Semana 3:
  └── 4.1 → 4.2 → 4.3 → 4.4 (comunidad, PIN, votación)
  └── 5.1 → 5.2 (verificación)

Semana 4:
  └── 6.1 → 6.2 (shared)
  └── 7.1 (legal)
  └── Pruebas, seed data de Bogotá, deploy
```

---

## 🚫 Explícitamente fuera del alcance v1

| Funcionalidad | Motivo |
|---------------|--------|
| Donaciones / gestión de dinero | Riesgo legal y de confianza; el core es informacional |
| Chat / mensajería interna | Complejidad sin retorno para el MVP |
| WhatsApp Cloud API | Costo de API business, no hay presupuesto |
| Cuentas de usuario individuales | No son necesarias; el PIN cubre la trazabilidad mínima |
| Dashboard público de impacto | Post-MVP, cuando haya datos que mostrar |
| API pública REST | Post-MVP, cuando haya consumidores externos |

---

## 📊 Métricas de éxito

Estas métricas definen si el proyecto realmente está ayudando. No son "vanidad" (visitas totales), son datos de **utilidad real**.

| Métrica | Cómo se mide | Objetivo v1 |
|---------|-------------|-------------|
| **Jornadas confirmadas** | % de campañas con ≥1 update comunitario | > 30% |
| **Fuentes activas** | Fuentes con datos actualizados en los últimos 60 días | > 5 |
| **Cobertura geográfica** | # municipios con ≥1 fuente verificada | > 3 |
| **Frescura del dato** | % de jornadas dentro del umbral de 5 días | > 80% |
| **Búsquedas útiles** | % de búsquedas que devuelven ≥1 resultado | > 60% |

---

## 🔄 Política de frescura (gobernanza del dato)

- Una jornada o punto fijo se considera **"no confirmado"** si pasaron más de 5 días desde `last_confirmed_at`.
- Mientras está no confirmado, se muestra con una advertencia visual: "Este dato no se ha confirmado recientemente. Verifica antes de ir."
- Si pasan más de 15 días sin confirmación, el dato se oculta de los resultados principales (sigue visible en búsqueda explícita).
- La comunidad puede confirmar datos usando el sistema de PIN y votación.

## ⚖️ Conflicto comunidad vs. fuente oficial

1. Un miembro de la comunidad reporta una actualización (ej: "la jornada se canceló").
2. Otros miembros pueden votar para respaldar ese reporte.
3. Si los votos alcanzan `COMMUNITY_VOTE_THRESHOLD` (default: 5):
   - El estado oficial se actualiza al reportado por la comunidad.
   - Se notifica a la fuente por correo.
4. Si no se alcanza el umbral:
   - El reporte queda visible pero el estado oficial NO cambia.
   - Prevalece la fuente oficial.

---

## 📁 Estructura de archivos (referencia rápida)

```
sos-animales/
├── app/
│   ├── main.py              # FastAPI app, monta routers
│   ├── config.py            # Settings desde .env
│   ├── database.py          # Engine + session async
│   │
│   ├── domains/
│   │   ├── sterilization/   # Jornadas y puntos fijos
│   │   ├── sources/          # Fundaciones/refugios
│   │   ├── verification/    # Proceso de verificación
│   │   ├── animals/         # Perfiles de animales
│   │   └── community/       # Actualizaciones con PIN
│   │
│   ├── shared/              # Código compartido
│   │   ├── geo.py           # Geocoding Nominatim
│   │   ├── security.py      # Hash PIN, rate limit
│   │   └── templates/       # Layouts y legales
│   │
│   └── static/              # CSS/JS extra
│
├── migrations/              # Alembic
├── tests/                   # Tests por dominio
├── pyproject.toml
├── .env.example
├── README.md
├── ROADMAP.md               ← estás aquí
├── LICENSE (AGPL-3.0)
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
└── SECURITY.md
```

---

## ✅ Checklist de finalización de Fase 1

- [ ] 0.1 Entorno y dependencias listos
- [ ] 0.2 PostgreSQL conectado
- [ ] 0.3 Alembic funcional
- [ ] 0.4 StaticFiles + templates base
- [ ] 1.1 Tabla sources creada
- [ ] 1.2 Formulario de registro funcional
- [ ] 1.3 Perfil público de fuente
- [ ] 2.1 Tablas campaigns + fixed_points creadas
- [ ] 2.2 Funciones de búsqueda implementadas
- [ ] 2.3 Página de búsqueda con HTMX funcional
- [ ] 2.4 Mapa Leaflet con pines
- [ ] 2.5 Detalle de campaña + tarjetas
- [ ] 3.1 Tabla animal_profiles creada
- [ ] 3.2 Formulario de alta con foto a R2
- [ ] 3.3 Listado y detalle de animales
- [ ] 4.1 Tabla community_updates creada
- [ ] 4.2 PIN generado y enviado por correo
- [ ] 4.3 Reporte comunitario funcional
- [ ] 4.4 Votación con umbral configurable
- [ ] 5.1 Tablas de verificación creadas
- [ ] 5.2 Checklist de verificación funcional
- [ ] 6.1 Geocoding con Nominatim
- [ ] 6.2 Hash de PIN + rate limiting
- [ ] 7.1 Avisos legales en formularios
- [ ] Tests pasando (pytest)
- [ ] Seed data de Bogotá cargada
- [ ] Deploy en producción
