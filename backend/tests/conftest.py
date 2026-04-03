"""Pytest configuration and fixtures for backend tests."""

import os
import sys
from unittest.mock import MagicMock, patch
import pytest

# Set environment variables BEFORE importing any modules
os.environ.setdefault("OPENAI_API_KEY", "test-key-12345")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test-aws-key")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test-aws-secret")
os.environ.setdefault("AWS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("CHAT_API_KEY", "test-chat-key")

