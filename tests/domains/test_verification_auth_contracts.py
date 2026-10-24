"""Integration, contract, and edge-case tests for Verification, Sources, and Auth Middleware.

Target coverage modules:
- app/domains/verification/router.py
- app/domains/sources/router.py
- app/domains/auth/middleware.py
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.config import settings
from app.database import get_db
from app.domains.animals.models import AnimalProfile
from app.domains.auth.middleware import get_current_admin, require_auth
from app.domains.sources.models import Source
from app.domains.sterilization.models import Campaign
from app.domains.verification.models import ChecklistResult, VerificationRequest, Visit
from app.main import app

# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------


def create_test_token(
    sub: str | None = "admin",
    expired: bool = False,
    secret: str = settings.JWT_SECRET,
    delta: timedelta | None = None,
) -> str:
    """Generate JWT tokens for testing various auth conditions."""
    if expired:
        exp = datetime.now(UTC) - timedelta(hours=2)
    elif delta is not None:
        exp = datetime.now(UTC) + delta
    else:
        exp = datetime.now(UTC) + timedelta(hours=2)

    payload: dict[str, str | datetime] = {"exp": exp}
    if sub is not None:
        payload["sub"] = sub

    return jwt.encode(payload, secret, algorithm="HS256")


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Test HTTP client with get_db dependency overridden to use test transaction."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_active_source(db_session: AsyncSession) -> Source:
    """Create an active pending shelter source."""
    source = Source(
        name="Albergue Esperanza Canina",
        type="verified_shelter",
        status="pending",
        municipality="Bogotá",
        department="Cundinamarca",
        contact_email="esperanza@example.org",
        contact_whatsapp="+573001112233",
        is_active=True,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest_asyncio.fixture
async def sample_inactive_source(db_session: AsyncSession) -> Source:
    """Create an inactive shelter source."""
    source = Source(
        name="Refugio Clausurado",
        type="community",
        status="pending",
        municipality="Cali",
        department="Valle del Cauca",
        is_active=False,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest_asyncio.fixture
async def sample_visit(db_session: AsyncSession, sample_active_source: Source) -> Visit:
    """Create a verification request and scheduled inspection visit."""
    v_req = VerificationRequest(
        source_id=sample_active_source.id,
        status="scheduled",
        submitted_evidence="Documentos sanitarios y fotos de instalaciones",
    )
    db_session.add(v_req)
    await db_session.commit()
    await db_session.refresh(v_req)

    visit = Visit(
        verification_request_id=v_req.id,
        visit_type="presencial",
        scheduled_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        visitor_name="Dra. Valentina Gómez",
    )
    db_session.add(visit)
    await db_session.commit()
    await db_session.refresh(visit)
    return visit


# ---------------------------------------------------------------------------
# Target 1: Auth Middleware Unit & Contract Tests (app/domains/auth/middleware.py)
# ---------------------------------------------------------------------------


class TestAuthMiddleware:
    """Rigorous tests covering every line and branch of require_auth and get_current_admin."""

    @pytest.mark.asyncio
    async def test_require_auth_missing_cookie(self) -> None:
        """require_auth raises 401 when access_token cookie is absent."""
        request = Request({"type": "http", "headers": []})
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "No autenticado"

    @pytest.mark.asyncio
    async def test_require_auth_expired_token(self) -> None:
        """require_auth raises 401 with 'Sesión expirada' when token is expired."""
        token = create_test_token(sub="admin", expired=True)
        request = Request(
            {"type": "http", "headers": [(b"cookie", f"access_token={token}".encode())]}
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Sesión expirada"

    @pytest.mark.asyncio
    async def test_require_auth_invalid_tampered_token(self) -> None:
        """require_auth raises 401 with 'Token inválido' when token signature fails."""
        token = create_test_token(sub="admin", secret="wrong_signature_secret")
        request = Request(
            {"type": "http", "headers": [(b"cookie", f"access_token={token}".encode())]}
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token inválido"

    @pytest.mark.asyncio
    async def test_require_auth_malformed_token_string(self) -> None:
        """require_auth raises 401 with 'Token inválido' when token is not valid JWT format."""
        request = Request(
            {"type": "http", "headers": [(b"cookie", b"access_token=not.a.valid.jwt")]}
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token inválido"

    @pytest.mark.asyncio
    async def test_require_auth_non_admin_sub(self) -> None:
        """require_auth raises 401 with 'Token inválido' when sub claim != 'admin'."""
        token = create_test_token(sub="regular_user")
        request = Request(
            {"type": "http", "headers": [(b"cookie", f"access_token={token}".encode())]}
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token inválido"

    @pytest.mark.asyncio
    async def test_require_auth_missing_sub(self) -> None:
        """require_auth raises 401 with 'Token inválido' when sub claim is omitted."""
        token = create_test_token(sub=None)
        request = Request(
            {"type": "http", "headers": [(b"cookie", f"access_token={token}".encode())]}
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token inválido"

    @pytest.mark.asyncio
    async def test_require_auth_valid_admin(self) -> None:
        """require_auth succeeds (returns None) when valid admin token is provided."""
        token = create_test_token(sub="admin")
        request = Request(
            {"type": "http", "headers": [(b"cookie", f"access_token={token}".encode())]}
        )
        await require_auth(request)

    @pytest.mark.asyncio
    async def test_get_current_admin_no_cookie(self) -> None:
        """get_current_admin returns False when cookie is missing."""
        request = Request({"type": "http", "headers": []})
        assert await get_current_admin(request) is False

    @pytest.mark.asyncio
    async def test_get_current_admin_expired_token(self) -> None:
        """get_current_admin returns False on expired token."""
        token = create_test_token(sub="admin", expired=True)
        request = Request(
            {"type": "http", "headers": [(b"cookie", f"access_token={token}".encode())]}
        )
        assert await get_current_admin(request) is False

    @pytest.mark.asyncio
    async def test_get_current_admin_invalid_token(self) -> None:
        """get_current_admin returns False on tampered or malformed token."""
        token = create_test_token(sub="admin", secret="invalid_secret_key")
        request = Request(
            {"type": "http", "headers": [(b"cookie", f"access_token={token}".encode())]}
        )
        assert await get_current_admin(request) is False

    @pytest.mark.asyncio
    async def test_get_current_admin_non_admin_sub(self) -> None:
        """get_current_admin returns False when token is valid but sub != 'admin'."""
        token = create_test_token(sub="moderator")
        request = Request(
            {"type": "http", "headers": [(b"cookie", f"access_token={token}".encode())]}
        )
        assert await get_current_admin(request) is False

    @pytest.mark.asyncio
    async def test_get_current_admin_valid_admin(self) -> None:
        """get_current_admin returns True for valid admin JWT."""
        token = create_test_token(sub="admin")
        request = Request(
            {"type": "http", "headers": [(b"cookie", f"access_token={token}".encode())]}
        )
        assert await get_current_admin(request) is True

    @pytest.mark.asyncio
    async def test_admin_route_redirect_missing_cookie(
        self, async_client: AsyncClient
    ) -> None:
        """GET /admin/ without auth cookie redirects to /auth/login (HTTP 302)."""
        response = await async_client.get("/admin/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers.get("location") == "/auth/login"

    @pytest.mark.asyncio
    async def test_admin_bare_path_redirects(self, async_client: AsyncClient) -> None:
        """GET /admin without trailing slash redirects to /admin/ then to /auth/login."""
        response = await async_client.get("/admin", follow_redirects=False)
        assert response.status_code in (307, 308)
        assert response.headers.get("location") in ("/admin/", "http://test/admin/")

        # Following redirects lands on /auth/login
        full_response = await async_client.get("/admin", follow_redirects=True)
        assert full_response.status_code == 200
        assert (
            "login" in full_response.text.lower()
            or "admin" in full_response.text.lower()
        )

    @pytest.mark.asyncio
    async def test_admin_route_redirect_expired_cookie(
        self, async_client: AsyncClient
    ) -> None:
        """GET /admin/ with expired token cookie redirects to /auth/login."""
        expired_token = create_test_token(sub="admin", expired=True)
        response = await async_client.get(
            "/admin/",
            cookies={"access_token": expired_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/auth/login"

    @pytest.mark.asyncio
    async def test_admin_route_redirect_tampered_cookie(
        self, async_client: AsyncClient
    ) -> None:
        """GET /admin/ with tampered token cookie redirects to /auth/login."""
        tampered_token = create_test_token(sub="admin", secret="fake_secret")
        response = await async_client.get(
            "/admin/",
            cookies={"access_token": tampered_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/auth/login"

    @pytest.mark.asyncio
    async def test_admin_route_redirect_non_admin_token(
        self, async_client: AsyncClient
    ) -> None:
        """GET /admin/ with non-admin token redirects to /auth/login."""
        user_token = create_test_token(sub="guest")
        response = await async_client.get(
            "/admin/",
            cookies={"access_token": user_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/auth/login"

    @pytest.mark.asyncio
    async def test_admin_route_authorized_success(
        self, async_client: AsyncClient
    ) -> None:
        """GET /admin/ with valid admin token loads admin panel with HTTP 200."""
        valid_token = create_test_token(sub="admin")
        response = await async_client.get(
            "/admin/",
            cookies={"access_token": valid_token},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert (
            "Panel de Administración" in response.text
            or "admin" in response.text.lower()
        )


# ---------------------------------------------------------------------------
# Target 2: Verification Router Tests (app/domains/verification/router.py)
# ---------------------------------------------------------------------------


class TestVerificationRouter:
    """Rigorous tests covering all lines and branches in app/domains/verification/router.py."""

    @pytest.mark.asyncio
    async def test_post_verification_request_unauthenticated(
        self, async_client: AsyncClient, sample_active_source: Source
    ) -> None:
        """POST /verification/request without authentication redirects to login."""
        response = await async_client.post(
            "/verification/request",
            data={"source_id": sample_active_source.id, "evidence": "Fotos"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/auth/login"

    @pytest.mark.asyncio
    async def test_post_verification_request_source_not_found(
        self, async_client: AsyncClient
    ) -> None:
        """POST /verification/request with non-existent source_id returns 404 error_not_found."""
        admin_token = create_test_token(sub="admin")
        response = await async_client.post(
            "/verification/request",
            data={"source_id": 999999, "evidence": "Comprobantes"},
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 404
        assert "Fuente no encontrada" in response.text

    @pytest.mark.asyncio
    async def test_post_verification_request_inactive_source(
        self, async_client: AsyncClient, sample_inactive_source: Source
    ) -> None:
        """POST /verification/request with inactive source returns 404 error_not_found."""
        admin_token = create_test_token(sub="admin")
        response = await async_client.post(
            "/verification/request",
            data={"source_id": sample_inactive_source.id, "evidence": "Comprobantes"},
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 404
        assert "Fuente no encontrada" in response.text

    @pytest.mark.asyncio
    async def test_post_verification_request_success(
        self,
        async_client: AsyncClient,
        sample_active_source: Source,
        db_session: AsyncSession,
    ) -> None:
        """POST /verification/request successfully creates pending verification request."""
        admin_token = create_test_token(sub="admin")
        response = await async_client.post(
            "/verification/request",
            data={
                "source_id": sample_active_source.id,
                "evidence": "Certificados de vacunación y fotos del predio",
            },
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 200
        assert "Solicitud" in response.text
        assert "pendiente" in response.text.lower()

    @pytest.mark.asyncio
    async def test_post_verification_request_tool_value_error(
        self, async_client: AsyncClient, sample_active_source: Source
    ) -> None:
        """POST /verification/request handles ValueError from tools layer with HTTP 400."""
        admin_token = create_test_token(sub="admin")
        with patch(
            "app.domains.verification.router.create_verification_request",
            side_effect=ValueError("La fuente ya cuenta con una solicitud activa"),
        ):
            response = await async_client.post(
                "/verification/request",
                data={"source_id": sample_active_source.id, "evidence": "Fotos"},
                cookies={"access_token": admin_token},
            )
        assert response.status_code == 400
        assert "La fuente ya cuenta con una solicitud activa" in response.text

    @pytest.mark.asyncio
    async def test_get_checklist_form_not_found(
        self, async_client: AsyncClient
    ) -> None:
        """GET /verification/visits/{visit_id}/checklist returns 404 if visit does not exist."""
        response = await async_client.get("/verification/visits/888888/checklist")
        assert response.status_code == 404
        assert "Visita no encontrada" in response.text

    @pytest.mark.asyncio
    async def test_get_checklist_form_found(
        self, async_client: AsyncClient, sample_visit: Visit
    ) -> None:
        """GET /verification/visits/{visit_id}/checklist renders checklist form successfully."""
        response = await async_client.get(
            f"/verification/visits/{sample_visit.id}/checklist"
        )
        assert response.status_code == 200
        assert "Evaluación Veterinaria" in response.text or "Checklist" in response.text
        assert str(sample_visit.id) in response.text

    @pytest.mark.asyncio
    async def test_submit_checklist_unauthenticated(
        self, async_client: AsyncClient, sample_visit: Visit
    ) -> None:
        """POST /verification/visits/{visit_id}/checklist without auth redirects to login."""
        response = await async_client.post(
            f"/verification/visits/{sample_visit.id}/checklist",
            data={"crit_1": "true", "crit_2": "true", "crit_3": "true"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/auth/login"

    @pytest.mark.asyncio
    async def test_submit_checklist_all_passed_with_global_notes(
        self,
        async_client: AsyncClient,
        sample_visit: Visit,
        sample_active_source: Source,
        db_session: AsyncSession,
    ) -> None:
        """POST /verification/visits/{id}/checklist when all pass approves source to verified."""
        admin_token = create_test_token(sub="admin")
        notes = "Instalaciones en perfecto estado higiénico y sanitario."
        response = await async_client.post(
            f"/verification/visits/{sample_visit.id}/checklist",
            data={
                "crit_1": "true",
                "crit_2": "true",
                "crit_3": "true",
                "global_notes": notes,
            },
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 200
        assert (
            "Verificación Exitosa" in response.text
            or "Aprobado" in response.text
            or "Estado de la Visita" in response.text
        )

        # Verify DB updates
        await db_session.refresh(sample_active_source)
        assert sample_active_source.status == "verified"
        assert sample_active_source.verified_at is not None

        # Verify checklist result has global notes attached to first criterion
        chks = (
            await db_session.execute(
                ChecklistResult.__table__.select().where(
                    ChecklistResult.visit_id == sample_visit.id
                )
            )
        ).fetchall()
        assert len(chks) == 3
        # First criterion has the global notes
        first_item = chks[0]
        assert first_item.notes == notes

    @pytest.mark.asyncio
    async def test_submit_checklist_rejected_without_notes(
        self,
        async_client: AsyncClient,
        sample_visit: Visit,
        sample_active_source: Source,
        db_session: AsyncSession,
    ) -> None:
        """POST /verification/visits/{id}/checklist when any criterion fails marks rejected."""
        admin_token = create_test_token(sub="admin")
        response = await async_client.post(
            f"/verification/visits/{sample_visit.id}/checklist",
            data={
                "crit_1": "true",
                "crit_2": "false",  # failing criterion
                "crit_3": "true",
            },
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 200
        assert (
            "Verificación Rechazada" in response.text
            or "Resultado de la Verificación" in response.text
        )

        # Source remains pending
        await db_session.refresh(sample_active_source)
        assert sample_active_source.status == "pending"

    @pytest.mark.asyncio
    async def test_post_verification_review_contract_endpoint(
        self, async_client: AsyncClient
    ) -> None:
        """Verify POST /verification/review returns 404 because review workflow uses POST /verification/visits/{visit_id}/checklist."""
        admin_token = create_test_token(sub="admin")
        response = await async_client.post(
            "/verification/review",
            json={"approved": True, "notes": "Approved via contract"},
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Target 3: Sources Router Tests (app/domains/sources/router.py)
# ---------------------------------------------------------------------------


class TestSourcesRouter:
    """Rigorous tests covering all lines and branches in app/domains/sources/router.py."""

    @pytest.mark.asyncio
    async def test_get_register_form_success(self, async_client: AsyncClient) -> None:
        """GET /sources/register renders the self-registration form."""
        response = await async_client.get("/sources/register")
        assert response.status_code == 200
        assert (
            "Registro de Fundación" in response.text
            or "Registra tu Refugio" in response.text
            or "register_form" in response.text
            or "Nombre de la Organización" in response.text
        )

    @pytest.mark.asyncio
    async def test_get_register_form_geo_exception_handling(
        self, async_client: AsyncClient
    ) -> None:
        """GET /sources/register gracefully handles get_grouped_municipalities exception."""
        with patch(
            "app.domains.sources.router.get_grouped_municipalities",
            side_effect=RuntimeError("Database/cache connection timeout"),
        ):
            response = await async_client.get("/sources/register")
        assert response.status_code == 200
        # Should render template with grouped_municipalities = {}

    @pytest.mark.asyncio
    async def test_post_register_form_success(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST /sources/register successfully registers new shelter and returns fragment."""
        payload = {
            "name": "Fundación Animalitos Sanos",
            "type": "official",
            "municipality": "Medellín",
            "department": "Antioquia",
            "accept_terms": "true",
            "contact_email": "contacto@animalitos.org",
            "contact_whatsapp": "+573109876543",
            "contact_url": "https://animalitos.org",
        }
        response = await async_client.post("/sources/register", data=payload)
        assert response.status_code == 200
        assert "Fundación Animalitos Sanos" in response.text
        assert (
            "Solicitud enviada con éxito" in response.text
            or "proceso de verificación" in response.text.lower()
        )

    @pytest.mark.asyncio
    async def test_post_register_form_invalid_type_error(
        self, async_client: AsyncClient
    ) -> None:
        """POST /sources/register with invalid type catches Pydantic validation and returns 400."""
        payload = {
            "name": "Refugio Sin Tipo Valido",
            "type": "tipo_inexistente",
            "municipality": "Bogotá",
            "department": "Cundinamarca",
            "accept_terms": "true",
        }
        response = await async_client.post("/sources/register", data=payload)
        assert response.status_code == 400
        assert "error" in response.text.lower() or "type" in response.text.lower()

    @pytest.mark.asyncio
    async def test_post_register_form_invalid_email_error(
        self, async_client: AsyncClient
    ) -> None:
        """POST /sources/register with malformed email catches validation error and returns 400."""
        payload = {
            "name": "Refugio Mal Email",
            "type": "community",
            "municipality": "Bogotá",
            "department": "Cundinamarca",
            "accept_terms": "true",
            "contact_email": "not-an-email-address",
        }
        response = await async_client.post("/sources/register", data=payload)
        assert response.status_code == 400
        assert "error" in response.text.lower() or "email" in response.text.lower()

    @pytest.mark.asyncio
    async def test_post_register_form_tool_exception_error(
        self, async_client: AsyncClient
    ) -> None:
        """POST /sources/register handles exception raised by register_source tool."""
        payload = {
            "name": "Refugio Duplicado Test",
            "type": "community",
            "municipality": "Cali",
            "department": "Valle",
            "accept_terms": "true",
        }
        with patch(
            "app.domains.sources.router.register_source",
            side_effect=ValueError("Nombre de refugio ya registrado"),
        ):
            response = await async_client.post("/sources/register", data=payload)
        assert response.status_code == 400
        assert "Nombre de refugio ya registrado" in response.text

    @pytest.mark.asyncio
    async def test_list_sources_view_all(
        self, async_client: AsyncClient, sample_active_source: Source
    ) -> None:
        """GET /sources and GET /sources/ return directory list with active sources."""
        response1 = await async_client.get("/sources")
        assert response1.status_code == 200
        assert (
            "Directorio de Albergues" in response1.text
            or sample_active_source.name in response1.text
        )

        response2 = await async_client.get("/sources/")
        assert response2.status_code == 200
        assert (
            "Directorio de Albergues" in response2.text
            or sample_active_source.name in response2.text
        )

    @pytest.mark.asyncio
    async def test_list_sources_view_filter_municipality(
        self, async_client: AsyncClient, sample_active_source: Source
    ) -> None:
        """GET /sources with municipality query param filters results."""
        # Query matching municipality
        resp_match = await async_client.get("/sources?municipality=Bogot")
        assert resp_match.status_code == 200
        assert sample_active_source.name in resp_match.text

        # Query non-matching municipality
        resp_empty = await async_client.get(
            "/sources?municipality=PuebloInexistente123"
        )
        assert resp_empty.status_code == 200
        assert sample_active_source.name not in resp_empty.text

    @pytest.mark.asyncio
    async def test_get_source_profile_not_found(
        self, async_client: AsyncClient
    ) -> None:
        """GET /sources/{id} returns 404 when source does not exist."""
        response = await async_client.get("/sources/999999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_source_profile_without_campaigns_or_animals(
        self, async_client: AsyncClient, sample_active_source: Source
    ) -> None:
        """GET /sources/{id} renders profile when source has no campaigns or animals."""
        response = await async_client.get(f"/sources/{sample_active_source.id}")
        assert response.status_code == 200
        assert sample_active_source.name in response.text

    @pytest.mark.asyncio
    async def test_get_source_profile_with_campaigns_and_animals(
        self,
        async_client: AsyncClient,
        sample_active_source: Source,
        db_session: AsyncSession,
    ) -> None:
        """GET /sources/{id} renders campaigns and animals associated with the shelter."""
        # Add campaign
        campaign = Campaign(
            source_id=sample_active_source.id,
            title="Jornada de Esterilización Gratuita Fontibón",
            municipality="Bogotá",
            species=["canino"],
            starts_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=5),
        )
        db_session.add(campaign)

        # Add animal profile
        animal = AnimalProfile(
            source_id=sample_active_source.id,
            name="Rocky El Valiente",
            species="canino",
            municipality="Bogotá",
            foto_url="https://r2.test/rocky.jpg",
            pin_hash="test_hashed_pin",
            status="available",
            is_sterilized=True,
        )
        db_session.add(animal)
        await db_session.commit()

        response = await async_client.get(f"/sources/{sample_active_source.id}")
        assert response.status_code == 200
        assert sample_active_source.name in response.text
        assert "Jornada de Esterilización Gratuita Fontibón" in response.text
        assert "Rocky El Valiente" in response.text
