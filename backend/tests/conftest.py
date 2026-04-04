"""Shared test configuration for backend tests.

Provides fixtures for testing with MessageQueue initialized.
AsyncClient from httpx does not automatically run lifespan context managers,
so we manually initialize the queue in these fixtures.
"""

import os
import warnings

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock

from backend.main import app, llm_client, s3_client, file_inputs_client
from backend.app.queue import MessageQueue
from backend.app.session import session_manager


def pytest_configure(config):
    """Warn if required environment variables are not set before test collection."""
    missing = []
    for var in ("OPENAI_API_KEY", "CHAT_API_KEY"):
        if not os.environ.get(var):
            missing.append(var)

    if missing:
        warnings.warn(
            f"Missing environment variables: {', '.join(missing)}. "
            "Tests that import backend.main will fail during collection. "
            "Create a .env file (see .env.example) or export the variables before running tests.",
            stacklevel=1,
        )


@pytest.fixture
async def app_with_queue():
    """Fixture that provides FastAPI app with MessageQueue initialized.
    
    Manually runs the lifespan startup to create and start MessageQueue,
    since AsyncClient from httpx does not run the context manager automatically.
    """
    # Startup: create and start queue
    queue_manager = MessageQueue(
        max_workers=2,  # Fewer workers for tests
        max_queue_size=10,
        llm_client=llm_client,
        s3_client=s3_client,
        file_inputs_client=file_inputs_client,
        session_manager=session_manager,
    )
    await queue_manager.start()
    app.state.queue_manager = queue_manager
    
    yield app
    
    # Shutdown: stop queue
    await queue_manager.stop()


@pytest.fixture
async def async_client_with_queue(app_with_queue):
    """AsyncClient that works with MessageQueue initialized.
    
    This client is connected to an app instance that has queue_manager
    in app.state, so tests can directly manipulate queue_manager.
    """
    async with AsyncClient(app=app_with_queue, base_url="http://test") as client:
        yield client


@pytest.fixture
def api_key_override():
    """Override API key verification for tests."""
    from backend.app.auth import verify_api_key
    app.dependency_overrides[verify_api_key] = lambda: "test_key"
    yield
    app.dependency_overrides.clear()

