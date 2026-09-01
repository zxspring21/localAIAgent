"""Route chat requests to the correct LLM client and model id."""

from openai import AsyncOpenAI

from app.config import settings
from app.llm.registry import ModelSpec, resolve_model

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


def attach_generation_extras(kwargs: dict, spec: ModelSpec) -> dict:
    """Add backend-specific params without breaking AsyncOpenAI type checks."""
    if spec.backend == "mlx":
        extra = dict(kwargs.get("extra_body") or {})
        extra.update(mlx_extra_body())
        kwargs["extra_body"] = extra
    return kwargs
