"""HTMX endpoints for the verification domain.

- POST /verification/request — submit verification request for an existing source.
- GET /verification/visits/{visit_id}/checklist — display inspection checklist for veterinarians.
- POST /verification/visits/{visit_id}/checklist — submit checklist evaluation results.
"""

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.domains.auth.middleware import require_auth
from app.domains.verification.tools import (
    record_checklist_result,
    create_verification_request,
)
from app.domains.sources.tools import get_source
from app.domains.verification.schemas import VerificationRequestCreate
from app.domains.verification.models import Visit

router = APIRouter(prefix="/verification", tags=["verification"])

templates = Jinja2Templates(
    directory=["app/domains/verification/templates", "app/shared/templates"]
)


@router.post("/request", response_class=HTMLResponse)
async def post_verification_request(
    request: Request,
    _: None = Depends(require_auth),
    source_id: int = Form(...),
    evidence: str | None = Form(None, max_length=10000),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Request verification for an existing source. Returns HTMX fragment."""
    # Validate with Pydantic before delegating to tools
    VerificationRequestCreate(source_id=source_id, evidence=evidence)

    source = await get_source(db, source_id)
    if not source or not source.is_active:
        return templates.TemplateResponse(
            request=request,
            name="error_not_found.html",
            context={"message": "Fuente no encontrada"},
            status_code=404,
        )

    try:
        req = await create_verification_request(db, source_id, evidence)
    except ValueError as e:
        return templates.TemplateResponse(
            request=request,
            name="error_not_found.html",
            context={"message": str(e)},
            status_code=400,
        )
    return templates.TemplateResponse(
        request=request,
        name="verification_request_success.html",
        context={"request_id": req.id, "status": "pendiente"},
    )


@router.get("/visits/{visit_id}/checklist", response_class=HTMLResponse)
async def get_checklist_form(
    request: Request,
    visit_id: int,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render the inspection checklist form for the visiting veterinarian."""
    visit = await db.execute(select(Visit).where(Visit.id == visit_id))
    if not visit.scalar_one_or_none():
        return templates.TemplateResponse(
            request=request,
            name="error_not_found.html",
            context={"message": "Visita no encontrada"},
            status_code=404,
        )
    return templates.TemplateResponse(
        request=request, name="checklist_form.html", context={"visit_id": visit_id}
    )


@router.post("/visits/{visit_id}/checklist", response_class=HTMLResponse)
async def submit_checklist(
    request: Request,
    visit_id: int,
    _: None = Depends(require_auth),
    crit_1: bool = Form(False),
    crit_2: bool = Form(False),
    crit_3: bool = Form(False),
    global_notes: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Process inspection checklist form and update verification status in database."""

    # Format inspection items matching tools layer expectation
    checklist_data = [
        {
            "criterion": "Instalaciones adecuadas, ventiladas y limpias",
            "passed": crit_1,
        },
        {
            "criterion": "Registros veterinarios (vacunas/desparasitación) al día",
            "passed": crit_2,
        },
        {"criterion": "Espacios seguros sin riesgo de fuga", "passed": crit_3},
    ]

    # Attach global notes to first criterion if provided
    if global_notes:
        checklist_data[0]["notes"] = global_notes

    # Execute business rule
    all_passed = await record_checklist_result(db, visit_id, checklist_data)

    return templates.TemplateResponse(
        request=request, name="visit_status.html", context={"all_passed": all_passed}
    )
