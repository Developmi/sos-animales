"""HTMX endpoints for the animals domain.

- GET /animals/new — creation form (sources/rescuers).
- POST /animals — create animal profile.
- GET /animals — catalog search filtered by municipality/species/status.
- GET /animals/{id} — detailed animal profile.
- POST /animals/{id}/adopt — mark animal as adopted with PIN.
"""

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Request,
    Depends,
    Form,
    File,
    UploadFile,
    Query,
    HTTPException,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from app.database import get_db
from app.domains.sources.models import Source
from app.shared.email import send_pin_email_sync
from app.shared.geo import get_grouped_municipalities
from app.shared.security import check_pin_rate_limit, record_failed_pin_attempt
from app.domains.animals.tools import (
    upload_photo_to_r2,
    upload_multiple_photos,
    validate_image_file,
    create_animal_profile,
    list_animals_by_filters,
    get_animal_detail,
    mark_as_adopted,
)
from app.config import settings
from app.domains.animals.schemas import AnimalCreate, AdoptAction

router = APIRouter(prefix="/animals", tags=["animals"])

templates = Jinja2Templates(
    directory=["app/domains/animals/templates", "app/shared/templates"]
)
templates.env.globals["settings"] = settings


@router.get("/", response_class=HTMLResponse)
async def search_animals_page(request: Request) -> HTMLResponse:
    """Render base search landing page for animals in adoption."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@router.get("/list", response_class=HTMLResponse)
async def get_animals_list_htmx(
    request: Request,
    municipality: str | None = Query(None),
    species: str | None = Query(None),
    status: str = Query("available"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """HTMX fragment returning the profile grid."""
    animals = await list_animals_by_filters(db, municipality, species, status=status)

    return templates.TemplateResponse(
        request=request, name="profile_list.html", context={"animals": animals}
    )


@router.get("/new", response_class=HTMLResponse)
async def new_animal_form(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """Render form to publish an animal for adoption."""
    try:
        grouped = await get_grouped_municipalities(db)
    except Exception:
        grouped = {}
    return templates.TemplateResponse(
        request=request,
        name="profile_form.html",
        context={"grouped_municipalities": grouped},
    )


def _render_animal_error_card(title: str, message: str) -> str:
    return f"""
    <div class="creation-card" style="max-width: 680px; margin: 30px auto; padding: 32px 24px; text-align: center; border-left: 4px solid #BE123C;">
      <div style="width: 48px; height: 48px; margin: 0 auto 16px; background: #FFF1F2; color: #BE123C; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 22px;">
        ⚠️
      </div>
      <h3 style="font-size: 20px; font-weight: 800; color: #9F1239; margin-bottom: 8px;">{title}</h3>
      <p style="font-size: 14px; color: var(--color-text-secondary); margin-bottom: 24px; line-height: 1.5;">{message}</p>
      <a href="/animals/new" class="btn-secondary" style="text-decoration: none; padding: 10px 20px; font-size: 13px;">
        ← Volver al Formulario
      </a>
    </div>
    """


def _render_animal_success_card(
    animal_id: int, animal_name: str, municipality: str, contact_email: str
) -> str:
    return f"""
    <div class="creation-card" style="text-align: center; padding: 48px 32px; max-width: 680px; margin: 30px auto;">
      <div style="width: 64px; height: 64px; margin: 0 auto 20px; background: rgba(13, 148, 136, 0.12); color: var(--color-teal); border: 2px solid var(--color-teal-border); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 28px;">
        ✓
      </div>

      <span class="brand-badge" style="background: rgba(13, 148, 136, 0.1); color: var(--color-teal); border: 1px solid var(--color-teal-border); border-radius: 9999px; padding: 4px 14px; font-weight: 700; font-size: 12px;">
        ¡PERFIL CREADO EXITOSAMENTE!
      </span>

      <h2 style="font-size: 28px; font-weight: 800; color: var(--color-text-main); margin: 14px 0 8px;">
        ¡{animal_name} ya está en adopción!
      </h2>

      <p style="font-size: 15px; color: var(--color-text-secondary); max-width: 520px; margin: 0 auto 24px; line-height: 1.6;">
        El caso ha sido registrado en la red nacional. La ciudadanía ya puede encontrarlo en el directorio de adopciones de <strong>{municipality.title()}</strong>.
      </p>

      <div style="background: #F8FAFC; border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 20px; margin-bottom: 32px; text-align: left; display: flex; gap: 14px; align-items: flex-start;">
        <div style="font-size: 24px; flex-shrink: 0;">🔑</div>
        <div>
          <strong style="color: var(--color-text-main); font-size: 14px;">PIN de Gestión Despachado:</strong>
          <p style="margin: 4px 0 0; font-size: 13px; color: var(--color-text-secondary); line-height: 1.5;">
            Enviamos el código PIN secreto de administración al correo <strong>{contact_email}</strong>.<br>
            Lo necesitarás cuando {animal_name} encuentre su familia definitiva para marcarlo como <em>Adoptado</em>.
          </p>
        </div>
      </div>

      <div style="display: flex; justify-content: center; gap: 14px; flex-wrap: wrap;">
        <a href="/animals/{animal_id}" class="btn-primary" style="text-decoration: none; padding: 12px 24px; font-size: 14px;">
          Ver Ficha de {animal_name} →
        </a>
        <a href="/animals/new" class="btn-secondary" style="text-decoration: none; padding: 12px 20px; font-size: 14px;">
          Publicar Otro Peludito
        </a>
      </div>
    </div>
    """


@router.post("/", response_class=HTMLResponse)
async def post_new_animal(
    request: Request,
    source_id: int = Form(...),
    name: str = Form(...),
    species: str = Form(...),
    municipality: str = Form(...),
    breed: str | None = Form(None),
    age_months: int | None = Form(None),
    age_years: int | None = Form(None),
    size: str | None = Form(None),
    is_sterilized: bool = Form(False),
    description: str | None = Form(None),
    foto: UploadFile = File(...),  # Primary (required)
    foto_2: UploadFile | None = File(None),  # Optional gallery photos
    foto_3: UploadFile | None = File(None),
    foto_4: UploadFile | None = File(None),
    foto_5: UploadFile | None = File(None),
    sexo: str | None = Form(None),
    fecha_nacimiento: date | None = Form(None),
    etapa_madurez: str | None = Form(None),
    condiciones_especiales: list[str] | None = Form(None),
    compatible_ninos: str | None = Form(None),
    compatible_otros_animales: str | None = Form(None),
    microchip: str | None = Form(None),
    source_url: str | None = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Process form submission, upload photo, generate PIN, and persist to database."""

    # 0. Validate that source exists and is active
    source_result = await db.execute(select(Source).where(Source.id == source_id))
    source = source_result.scalar_one_or_none()
    if not source or not source.is_active:
        return HTMLResponse(
            content=_render_animal_error_card(
                "Fuente no disponible",
                "La entidad u organización seleccionada no se encuentra activa en el sistema.",
            ),
            status_code=400,
        )

    # 1. Fast image validation: ensure every file is an image and <= 5MB BEFORE any upload
    all_uploads = [
        f for f in [foto, foto_2, foto_3, foto_4, foto_5] if f and f.filename
    ]
    for upload in all_uploads:
        try:
            validate_image_file(upload)
        except ValueError as err:
            return HTMLResponse(
                content=_render_animal_error_card("Archivo no permitido", str(err)),
                status_code=400,
            )

    # 2. Upload mandatory primary photo and optional gallery photos
    try:
        foto_url = await upload_photo_to_r2(foto)
    except Exception as e:
        return HTMLResponse(
            content=_render_animal_error_card("Error al procesar fotografía", str(e)),
            status_code=500,
        )
    extras = [f for f in [foto_2, foto_3, foto_4, foto_5] if f and f.filename]
    fotos_urls_list = await upload_multiple_photos(extras, max_files=4)

    # 3. Explicit species validation before further processing
    if species not in ["canino", "felino"]:
        return HTMLResponse(
            content=_render_animal_error_card(
                "Especie inválida",
                "Por favor selecciona una especie válida (canino o felino).",
            ),
            status_code=400,
        )

    # 4. Age calculation: derive age_years if age_months is provided
    if age_months is not None and age_years is None:
        age_years = age_months // 12 if age_months >= 12 else 0

    # 5. Validate with Pydantic schema before delegating to tools
    try:
        animal_data = AnimalCreate(
            name=name,
            species=species,
            municipality=municipality,
            breed=breed,
            age_months=age_months,
            age_years=age_years,
            size=size,
            is_sterilized=is_sterilized,
            description=description,
            sexo=sexo,
            fecha_nacimiento=fecha_nacimiento,
            etapa_madurez=etapa_madurez,
            condiciones_especiales=condiciones_especiales or None,
            compatible_ninos={"true": True, "false": False}.get(compatible_ninos or ""),
            compatible_otros_animales={"true": True, "false": False}.get(
                compatible_otros_animales or ""
            ),
            microchip=microchip,
            source_url=source_url,
        )
    except Exception as e:
        return HTMLResponse(
            content=_render_animal_error_card("Error en los datos ingresados", str(e)),
            status_code=400,
        )

    # 3. Persist entity in database and obtain PIN
    data_dict = animal_data.model_dump()
    data_dict["foto_urls"] = fotos_urls_list or None
    try:
        result = await create_animal_profile(db, source_id, data_dict, foto_url)
    except ValueError as e:
        return HTMLResponse(
            content=_render_animal_error_card("No fue posible crear el perfil", str(e)),
            status_code=400,
        )
    animal = result["animal"]
    pin = result["raw_pin"]

    # 4. Dispatch management PIN via email in background (zero plaintext exposure in HTML)
    contact_email = (
        source.contact_email
        if source and source.contact_email
        else "contacto@sos-animales.org"
    )
    background_tasks.add_task(send_pin_email_sync, contact_email, animal.name, pin)

    # 5. Return success confirmation without exposing plaintext PIN
    return HTMLResponse(
        content=_render_animal_success_card(
            animal.id, animal.name, animal.municipality, contact_email
        )
    )


@router.get("/{animal_id}", response_class=HTMLResponse)
async def animal_detail_page(
    request: Request, animal_id: int, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """Detailed profile view for an animal."""
    detail = await get_animal_detail(db, animal_id)

    if not detail:
        raise HTTPException(status_code=404, detail="Animal no encontrado")

    return templates.TemplateResponse(
        request=request,
        name="profile_detail.html",
        context={"animal": detail["animal"], "source": detail["source"]},
    )


@router.post("/{animal_id}/adopt", response_class=HTMLResponse)
async def adopt_animal(
    request: Request,
    animal_id: int,
    pin: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not await check_pin_rate_limit(
        client_ip, animal_id, max_attempts=5, window_seconds=3600
    ):
        return HTMLResponse(
            content="<div class='alert-box' style='color: #E11D48; padding: 12px; background: #FFF1F2; border-radius: 8px;'>Demasiados intentos fallidos. Por seguridad, espera unos minutos antes de intentar de nuevo.</div>",
            status_code=429,
        )

    # Validate PIN with schema
    AdoptAction(pin=pin)
    success = await mark_as_adopted(db, animal_id, pin)

    if success:
        return templates.TemplateResponse(
            request=request,
            name="adopt_success.html",
            context={"animal_id": animal_id},
        )
    else:
        await record_failed_pin_attempt(client_ip, animal_id, window_seconds=3600)
        return templates.TemplateResponse(
            request=request,
            name="adopt_error.html",
            context={},
        )
