"""Central model catalog — local MLX + cloud API providers."""

from dataclasses import dataclass
from enum import Enum

from app.config import settings


class ModelTier(str, Enum):
    FREE = "free"
    PAID = "paid"


class ModelProvider(str, Enum):
    META = "Meta"
    GOOGLE = "Google"
    OPENAI = "OpenAI"
    ANTHROPIC = "Anthropic"
    DEEPSEEK = "DeepSeek"
    MOONSHOT = "Moonshot (Kimi)"
    XAI = "xAI"
    QWEN = "Qwen"
    MLX = "MLX Local"


@dataclass(frozen=True)
class ModelSpec:
    id: str
    display_name: str
    provider: ModelProvider
    tier: ModelTier
    backend: str  # mlx | openai | anthropic | google
    api_model: str  # model id sent to the API
    local_mlx_id: str | None = None  # mlx-community repo (no HF gate)
    description: str = ""
    supports_tools: bool = False
    context_k: int = 8

    @property
    def available(self) -> bool:
        return _is_model_available(self)


def _is_model_available(spec: ModelSpec) -> bool:
    if spec.backend == "mlx":
        return settings.llm_backend == "mlx"
    key_map = {
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "google": settings.google_api_key,
        "deepseek": settings.deepseek_api_key,
        "moonshot": settings.moonshot_api_key,
        "xai": settings.xai_api_key,
    }
    return bool(key_map.get(spec.backend, ""))


# Aliases users might pick → canonical registry id
MODEL_ALIASES: dict[str, str] = {
    "meta-llama/Llama-3.1-8B-Instruct": "mlx-llama-3.1-8b",
    "meta-llama/Meta-Llama-3-8B-Instruct": "mlx-llama-3.2-3b",
    "meta-llama/Llama-3.2-3B-Instruct": "mlx-llama-3.2-3b",
    "default_model": "mlx-llama-3.2-3b",
}

MODEL_CATALOG: list[ModelSpec] = [
    # ── Local MLX (Apple Silicon, free) ──
    ModelSpec(
        id="mlx-llama-3.2-3b",
        display_name="Llama 3.2 3B (Local MLX)",
        provider=ModelProvider.META,
        tier=ModelTier.FREE,
        backend="mlx",
        api_model="mlx-community/Llama-3.2-3B-Instruct-4bit",
        local_mlx_id="mlx-community/Llama-3.2-3B-Instruct-4bit",
        description="Fast, 8GB RAM — best for MacBook Air M2",
        context_k=8,
    ),
    ModelSpec(
        id="mlx-llama-3.1-8b",
        display_name="Llama 3.1 8B (Local MLX)",
        provider=ModelProvider.META,
        tier=ModelTier.FREE,
        backend="mlx",
        api_model="mlx-community/Meta-Llama-3.1-8B-Instruct-4bit",
        local_mlx_id="mlx-community/Meta-Llama-3.1-8B-Instruct-4bit",
        description="Better quality, needs 16GB+ RAM",
        context_k=8,
    ),
    ModelSpec(
        id="mlx-gemma-2-9b",
        display_name="Gemma 2 9B (Local MLX)",
        provider=ModelProvider.GOOGLE,
        tier=ModelTier.FREE,
        backend="mlx",
        api_model="mlx-community/gemma-2-9b-it-4bit",
        local_mlx_id="mlx-community/gemma-2-9b-it-4bit",
        description="Google Gemma 2, 4-bit quantized",
        context_k=8,
    ),
    ModelSpec(
        id="mlx-qwen-7b",
        display_name="Qwen 2.5 7B (Local MLX)",
        provider=ModelProvider.QWEN,
        tier=ModelTier.FREE,
        backend="mlx",
        api_model="mlx-community/Qwen2.5-7B-Instruct-4bit",
        local_mlx_id="mlx-community/Qwen2.5-7B-Instruct-4bit",
        description="Strong multilingual model",
        context_k=32,
    ),
    ModelSpec(
        id="mlx-deepseek-r1",
        display_name="DeepSeek R1 Distill 7B (Local MLX)",
        provider=ModelProvider.DEEPSEEK,
        tier=ModelTier.FREE,
        backend="mlx",
        api_model="mlx-community/DeepSeek-R1-Distill-Qwen-7B-4bit",
        local_mlx_id="mlx-community/DeepSeek-R1-Distill-Qwen-7B-4bit",
        description="Reasoning-focused local model",
        context_k=32,
    ),
    # ── Cloud API (paid / free tier) ──
    ModelSpec(
        id="openai-gpt-4o",
        display_name="GPT-4o (OpenAI Cloud)",
        provider=ModelProvider.OPENAI,
        tier=ModelTier.PAID,
        backend="openai",
        api_model="gpt-4o",
        description="Latest OpenAI — set OPENAI_API_KEY",
        supports_tools=True,
        context_k=128,
    ),
    ModelSpec(
        id="anthropic-claude",
        display_name="Claude Sonnet (Anthropic)",
        provider=ModelProvider.ANTHROPIC,
        tier=ModelTier.PAID,
        backend="anthropic",
        api_model="claude-sonnet-4-20250514",
        description="Anthropic Claude — set ANTHROPIC_API_KEY",
        supports_tools=True,
        context_k=200,
    ),
    ModelSpec(
        id="google-gemini-flash",
        display_name="Gemini 2.0 Flash (Google)",
        provider=ModelProvider.GOOGLE,
        tier=ModelTier.FREE,
        backend="google",
        api_model="gemini-2.0-flash",
        description="Google AI — set GOOGLE_API_KEY",
        supports_tools=True,
        context_k=1000,
    ),
    ModelSpec(
        id="deepseek-chat",
        display_name="DeepSeek Chat (Cloud)",
        provider=ModelProvider.DEEPSEEK,
        tier=ModelTier.PAID,
        backend="deepseek",
        api_model="deepseek-chat",
        description="DeepSeek API — set DEEPSEEK_API_KEY",
        supports_tools=True,
        context_k=64,
    ),
    ModelSpec(
        id="moonshot-kimi",
        display_name="Kimi (Moonshot)",
        provider=ModelProvider.MOONSHOT,
        tier=ModelTier.PAID,
        backend="moonshot",
        api_model="moonshot-v1-8k",
        description="Moonshot Kimi — set MOONSHOT_API_KEY",
        supports_tools=True,
        context_k=8,
    ),
    ModelSpec(
        id="xai-grok",
        display_name="Grok (xAI)",
        provider=ModelProvider.XAI,
        tier=ModelTier.PAID,
        backend="xai",
        api_model="grok-beta",
        description="xAI Grok — set XAI_API_KEY",
        supports_tools=True,
        context_k=128,
    ),
]

_CATALOG_BY_ID = {m.id: m for m in MODEL_CATALOG}


def resolve_model(model_id: str) -> ModelSpec:
    """Map UI / legacy ids to a catalog entry."""
    canonical = MODEL_ALIASES.get(model_id, model_id)
    if canonical in _CATALOG_BY_ID:
        return _CATALOG_BY_ID[canonical]
    # Raw mlx-community id from MLX server
    for spec in MODEL_CATALOG:
        if spec.api_model == model_id or spec.local_mlx_id == model_id:
            return spec
    # Unknown — treat as raw MLX model on local server
    return ModelSpec(
        id=model_id,
        display_name=model_id,
        provider=ModelProvider.MLX,
        tier=ModelTier.FREE,
        backend="mlx",
        api_model=model_id,
        local_mlx_id=model_id,
    )


def list_catalog_models(include_unavailable: bool = True) -> list[ModelSpec]:
    if include_unavailable:
        return list(MODEL_CATALOG)
    return [m for m in MODEL_CATALOG if m.available]


def catalog_to_api_dict(spec: ModelSpec) -> dict:
    return {
        "id": spec.id,
        "name": spec.display_name,
        "provider": spec.provider.value,
        "tier": spec.tier.value,
        "backend": spec.backend,
        "api_model": spec.api_model,
        "available": spec.available,
        "supports_tools": spec.supports_tools,
        "description": spec.description,
        "context_k": spec.context_k,
    }
