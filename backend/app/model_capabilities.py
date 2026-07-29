"""Versioned, application-owned model capability registry.

The registry is intentionally static. Runtime code must not infer context or output
limits from optional fields returned by a provider's Models API.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping, Optional


MODEL_CAPABILITY_REGISTRY_VERSION: Final[str] = "2026-07-28"


@dataclass(frozen=True)
class ModelCapabilities:
    """Token limits and tokenizer pinned for a supported model identifier."""

    model: str
    context_window_tokens: int
    max_output_tokens: int
    encoding: str
    registry_version: str = MODEL_CAPABILITY_REGISTRY_VERSION


_GPT_5_4_NANO = ModelCapabilities(
    model="gpt-5.4-nano",
    context_window_tokens=400_000,
    max_output_tokens=128_000,
    encoding="o200k_base",
)
_GPT_5_4_NANO_SNAPSHOT = ModelCapabilities(
    model="gpt-5.4-nano-2026-03-17",
    context_window_tokens=400_000,
    max_output_tokens=128_000,
    encoding="o200k_base",
)

MODEL_CAPABILITIES: Final[Mapping[str, ModelCapabilities]] = MappingProxyType(
    {
        _GPT_5_4_NANO.model: _GPT_5_4_NANO,
        _GPT_5_4_NANO_SNAPSHOT.model: _GPT_5_4_NANO_SNAPSHOT,
    }
)


def get_model_capabilities(model: str) -> Optional[ModelCapabilities]:
    """Return pinned capabilities, or ``None`` for an unknown model."""
    return MODEL_CAPABILITIES.get(model)
