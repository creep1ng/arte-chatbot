"""Shared test configuration for backend tests.

Emits a warning if required environment variables are missing,
since FileInputsClient() is instantiated at module level in backend.main
and will raise FileUploadError without OPENAI_API_KEY.
"""

import os
import warnings


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
