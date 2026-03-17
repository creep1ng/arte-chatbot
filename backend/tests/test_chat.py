import os
import uuid

import pytest
import requests

API_URL = "http://localhost:8000/chat"


@pytest.fixture(scope="module")
def api_key():
    key = os.getenv("OPENAI_API_KEY")
    assert key is not None, "OPENAI_API_KEY must be set in environment"
    return key


def test_chat_status_200():
    """Verify the /chat endpoint returns 200 for a valid request (no auth header needed)."""
    payload = {"message": "Hello", "session_id": str(uuid.uuid4())}
    response = requests.post(API_URL, json=payload)
    assert response.status_code == 200


def test_chat_response_not_empty(api_key):
    """Verify the response body is non-empty when the API key is available."""
    payload = {"message": "Test", "session_id": str(uuid.uuid4())}
    response = requests.post(API_URL, json=payload)
    assert response.json().get("response"), "Response should not be empty"


def test_session_id_uuid_format(api_key):
    """Verify the returned session_id is a valid UUID."""
    session_id = str(uuid.uuid4())
    payload = {"message": "UUID check", "session_id": session_id}
    response = requests.post(API_URL, json=payload)
    returned_id = response.json().get("session_id")
    assert returned_id is not None
    try:
        uuid.UUID(returned_id)
    except ValueError:
        pytest.fail("session_id is not valid UUID format")


def test_openai_api_key_loaded_from_env():
    """Verify the OPENAI_API_KEY environment variable is set."""
    assert os.getenv("OPENAI_API_KEY") is not None, (
        "OPENAI_API_KEY must be loaded from environment"
    )
