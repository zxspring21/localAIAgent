"""Route chat requests to the correct LLM client and model id."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from app.config import settings
from app.llm.registry import ModelSpec, resolve_model

# OpenAI SDK rejects these as create() kwargs. MLX accepts them in the JSON body.
_MLX_ONLY_BODY_KEYS = ("repetition_penalty", "repetition_context_size")
_PENALTY_KEYS = ("frequency_penalty", "presence_penalty")

CLOUD_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "xai": "https://api.x.ai/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
}

CLOUD_API_KEYS = {
    "openai": lambda: settings.openai_api_key,
    "deepseek": lambda: settings.deepseek_api_key,
    "moonshot": lambda: settings.moonshot_api_key,
    "xai": lambda: settings.xai_api_key,
    "google": lambda: settings.google_api_key,
    "anthropic": lambda: settings.anthropic_api_key,
}


def get_api_model_id(spec: ModelSpec) -> str:
    if spec.backend == "mlx":
        return spec.local_mlx_id or spec.api_model
    return spec.api_model


def get_llm_client(spec: ModelSpec) -> AsyncOpenAI:
    if spec.backend == "mlx":
        return AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout,
        )

    if spec.backend == "anthropic":
        return AsyncOpenAI(
            base_url="https://api.anthropic.com/v1",
            api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout,
        )

    base = CLOUD_BASE_URLS.get(spec.backend)
    key_fn = CLOUD_API_KEYS.get(spec.backend)
    if not base or not key_fn or not key_fn():
        raise RuntimeError(
            f"Model '{spec.display_name}' requires {spec.backend.upper()}_API_KEY in .env"
        )

    return AsyncOpenAI(base_url=base, api_key=key_fn(), timeout=settings.llm_timeout)


def validate_model(model_id: str) -> tuple[ModelSpec, str]:
    spec = resolve_model(model_id)
    api_id = get_api_model_id(spec)
    if not spec.available and spec.backend != "mlx":
        raise RuntimeError(
            f"Model '{spec.display_name}' is not configured. "
            f"Add {spec.backend.upper()}_API_KEY to .env"
        )
    return spec, api_id


def use_tools_for_model(spec: ModelSpec) -> bool:
    if spec.backend == "mlx":
        return settings.llm_enable_tools
    return spec.supports_tools and settings.llm_enable_tools


def mlx_extra_body() -> dict:
    """MLX-only sampling knobs. Must go in extra_body — the OpenAI SDK rejects them as kwargs."""
    return {
        "repetition_penalty": settings.llm_repetition_penalty,
        "repetition_context_size": settings.llm_repetition_context_size,
    }


def sanitize_completion_kwargs(kwargs: dict[str, Any], spec: ModelSpec) -> dict[str, Any]:
    """Never pass repetition_penalty as a Python kwarg to AsyncCompletions.create()."""
    out = dict(kwargs)
    extra = dict(out.pop("extra_body", None) or {})

    for key in _MLX_ONLY_BODY_KEYS:
        if key in out:
            extra[key] = out.pop(key)

    if spec.backend == "mlx":
        extra.update(mlx_extra_body())
    else:
        for key in _MLX_ONLY_BODY_KEYS:
            extra.pop(key, None)

    if spec.backend in ("google", "anthropic"):
        for key in _PENALTY_KEYS:
            out.pop(key, None)

    if extra:
        out["extra_body"] = extra
    return out


def attach_generation_extras(kwargs: dict, spec: ModelSpec) -> dict:
    """Add backend-specific params without breaking AsyncOpenAI type checks."""
    return sanitize_completion_kwargs(kwargs, spec)


async def create_chat_completion(client: AsyncOpenAI, spec: ModelSpec, **kwargs: Any):
    """Single entry for chat.completions.create with SDK-safe kwargs."""
    return await client.chat.completions.create(**sanitize_completion_kwargs(kwargs, spec))
