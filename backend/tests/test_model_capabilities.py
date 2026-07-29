"""Tests for the versioned model capability registry."""

from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from backend.app.model_capabilities import (
    MODEL_CAPABILITIES,
    MODEL_CAPABILITY_REGISTRY_VERSION,
    ModelCapabilities,
    get_model_capabilities,
)


@pytest.mark.parametrize(
    "model",
    ("gpt-5.4-nano", "gpt-5.4-nano-2026-03-17"),
)
def test_registry_contains_versioned_model_capabilities(model: str) -> None:
    capabilities = get_model_capabilities(model)

    assert capabilities is not None
    assert capabilities.model == model
    assert capabilities.context_window_tokens == 400_000
    assert capabilities.max_output_tokens == 128_000
    assert capabilities.encoding == "o200k_base"
    assert capabilities.registry_version == MODEL_CAPABILITY_REGISTRY_VERSION


def test_unknown_model_returns_none() -> None:
    assert get_model_capabilities("unknown-model") is None


def test_registry_mapping_is_immutable() -> None:
    with pytest.raises(TypeError):
        with patch.dict(MODEL_CAPABILITIES, {}, clear=True):
            pass


def test_model_capabilities_are_immutable() -> None:
    capabilities = ModelCapabilities(
        model="test-model",
        context_window_tokens=1,
        max_output_tokens=1,
        encoding="test-encoding",
    )

    with pytest.raises(FrozenInstanceError):
        setattr(capabilities, "context_window_tokens", 2)
