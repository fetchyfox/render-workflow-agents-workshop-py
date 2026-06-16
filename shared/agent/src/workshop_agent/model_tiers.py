"""Model tier mapping. One place to update when new models ship."""

from __future__ import annotations

from typing import Literal

from .helpers import infer_provider, is_tier
from .types import ModelSpec, Provider

ModelTier = Literal["small", "medium", "large"]

MODEL_TIERS: dict[ModelTier, ModelSpec] = {
    "small": ModelSpec(provider=Provider.ANTHROPIC, model="claude-haiku-4-5"),
    "medium": ModelSpec(provider=Provider.ANTHROPIC, model="claude-sonnet-4-6"),
    "large": ModelSpec(provider=Provider.ANTHROPIC, model="claude-opus-4-6"),
}


def resolve_model_spec(model: str | None = None, provider: str | None = None) -> ModelSpec:
    model_name = model or "medium"
    if is_tier(model_name):
        return MODEL_TIERS[model_name].model_copy()  # type: ignore[arg-type]
    return ModelSpec(
        provider=Provider(provider) if provider else Provider(infer_provider(model_name)),
        model=model_name,
    )
