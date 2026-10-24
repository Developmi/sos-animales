"""Tests for FastAPI lifespan integration in main.py.

Verifies that the app initializes Valkey on startup and serves requests.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Create a TestClient that triggers the lifespan."""
    from app.main import app

    with TestClient(app) as tc:
        yield tc


def test_app_has_lifespan() -> None:
    """The FastAPI app should have a lifespan configured."""
    from app.main import app

    assert app.router.lifespan_context is not None, (
        "App must have lifespan configured for Valkey init/close"
    )


def test_root_endpoint_works(client: TestClient) -> None:
    """The root endpoint should return 200 after lifespan startup."""
    response = client.get("/")
    assert response.status_code == 200


def test_valkey_initialized_after_startup(client: TestClient) -> None:
    """After lifespan startup, geo.valkey_client should be initialized."""
    from app.shared import geo

    assert geo.valkey_client is not None, (
        "Valkey client must be initialized by lifespan before any request"
    )


def test_app_state_valkey_set(client: TestClient) -> None:
    """After lifespan startup, app.state.valkey should hold the client."""
    from app.main import app
    from app.shared import geo

    valkey = getattr(app.state, "valkey", None)
    assert valkey is not None, "app.state.valkey must be set by lifespan"
    assert valkey is geo.valkey_client, (
        "app.state.valkey must reference the same client as geo.valkey_client"
    )
