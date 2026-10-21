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
from app.shared.security import check_pin_rate_limit, record_failed_pin_attempt
from app.domains.animals.tools import (
    upload_photo_to_r2,
    upload_multiple_photos,
    create_animal_profile,
    list_animals_by_filters,
    get_animal_detail,
    mark_as_adopted,
)
from app.domains.animals.schemas import AnimalCreate, AdoptAction

router = APIRouter(prefix="/animals", tags=["animals"])

templates = Jinja2Templates(
    directory=["app/domains/animals/templates", "app/shared/templates"]
)


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
async def new_animal_form(request: Request) -> HTMLResponse:
    """Render form to publish an animal for adoption."""
    return templates.TemplateResponse(
        request=request, name="profile_form.html", context={}
    )


@router.post("/", response_class=HTMLResponse)
async def post_new_animal(
    request: Request,
    source_id: int = Form(...),
    name: str = Form(...),
    species: str = Form(...),
    municipality: str = Form(...),
    breed: str | None = Form(None),
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
            content="<article><header>Error</header><p>Fuente no encontrada o inactiva</p></article>",
            status_code=400,
        )

    # 1. Upload mandatory primary photo and optional gallery photos
    try:
        foto_url = await upload_photo_to_r2(foto)
    except Exception as e:
        return HTMLResponse(
            content=f"<article><header>Error al subir foto</header><p>{str(e)}</p></article>",
            status_code=500,
        )
    extras = [f for f in [foto_2, foto_3, foto_4, foto_5] if f and f.filename]
    fotos_urls_list = await upload_multiple_photos(extras, max_files=4)

    # 2. Explicit species validation before further processing
    if species not in ["canino", "felino"]:
        return HTMLResponse(
            content="<article><header>Error</header><p>Especie inválida. Debe ser canino o felino.</p></article>",
            status_code=400,
        )

    # 2b. Validate with Pydantic schema before delegating to tools
    try:
        animal_data = AnimalCreate(
            name=name,
            species=species,
            municipality=municipality,
            breed=breed,
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
            content=f"<article><header>Error de Validación</header><p>{str(e)}</p></article>",
            status_code=400,
        )

    # 3. Persist entity in database and obtain PIN
    data_dict = animal_data.model_dump()
    data_dict["foto_urls"] = fotos_urls_list or None
    try:
        result = await create_animal_profile(db, source_id, data_dict, foto_url)
    except ValueError as e:
        return HTMLResponse(
            content=f"<article><header>Error</header><p>{str(e)}</p></article>",
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
        content=f"<article><header style='background-color: var(--pico-primary-background); color: white;'>¡Perfil Creado!</header>"
        f"El peludito <strong>{animal.name}</strong> está publicado.<br><br>"
        f"✅ <strong>Te enviamos el PIN de administración al correo:</strong> <mark>{contact_email}</mark><br>"
        f"<small>Revisa tu bandeja de entrada o spam. Lo necesitarás si deseas marcar a {animal.name} como adoptado.</small></article>"
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
