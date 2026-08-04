from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_secret_key: str = "change-me"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8080

    # LLM backend: mlx (Apple Silicon) | vllm (NVIDIA GPU) | ollama
    llm_backend: str = "mlx"
    llm_base_url: str = "http://localhost:8000/v1"
    llm_default_model: str = "mlx-llama-3.2-3b"
    llm_api_key: str = "mlx"
    llm_timeout: float = 180.0
    llm_max_tokens: int = 2048
    llm_enable_tools: bool = False

    # Legacy aliases (still read from .env)
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_default_model: str = "mlx-community/Llama-3.2-3B-Instruct-4bit"
    vllm_api_key: str = "mlx"

    database_url: str = "postgresql+asyncpg://localai:localai@localhost:5432/localai"
    redis_url: str = "redis://localhost:6379/0"

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "user_memory"

    embedding_base_url: str = "http://localhost:8000/v1"
    embedding_model: str = "text-embedding-3-small"

    jwt_secret_key: str = "change-me-jwt"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    st_memory_max_messages: int = 20
    lt_memory_retrieval_limit: int = 5

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    tavily_api_key: str = ""
    tavily_mcp_url: str = ""
    serpapi_api_key: str = ""
    web_search_provider: str = "duckduckgo"

    # Cloud LLM API keys (optional — enables paid/cloud models in catalog)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    deepseek_api_key: str = ""
    moonshot_api_key: str = ""
    xai_api_key: str = ""

    # Hugging Face token (for gated models if using raw HF ids)
    hf_token: str = ""

    # MCP server URLs (optional integrations)
    mcp_slack_url: str = ""
    mcp_notion_url: str = ""
    mcp_gmail_url: str = ""

    max_cot_iterations: int = 10
    max_swarm_agents: int = 3
    frontend_url: str = "http://localhost:3000"

    def model_post_init(self, __context) -> None:
        import os

        # Prefer LLM_* env vars; fall back to legacy VLLM_*
        if os.getenv("LLM_BASE_URL"):
            object.__setattr__(self, "llm_base_url", os.getenv("LLM_BASE_URL", self.llm_base_url))
        elif os.getenv("VLLM_BASE_URL"):
            object.__setattr__(self, "llm_base_url", os.getenv("VLLM_BASE_URL", self.llm_base_url))

        if os.getenv("LLM_DEFAULT_MODEL"):
            object.__setattr__(self, "llm_default_model", os.getenv("LLM_DEFAULT_MODEL", self.llm_default_model))
        elif os.getenv("VLLM_DEFAULT_MODEL"):
            object.__setattr__(self, "llm_default_model", os.getenv("VLLM_DEFAULT_MODEL", self.llm_default_model))

        if os.getenv("LLM_API_KEY"):
            object.__setattr__(self, "llm_api_key", os.getenv("LLM_API_KEY", self.llm_api_key))
        elif os.getenv("VLLM_API_KEY"):
            object.__setattr__(self, "llm_api_key", os.getenv("VLLM_API_KEY", self.llm_api_key))

        if os.getenv("LLM_BACKEND"):
            object.__setattr__(self, "llm_backend", os.getenv("LLM_BACKEND", self.llm_backend))

        if not self.tavily_mcp_url and self.tavily_api_key:
            object.__setattr__(
                self,
                "tavily_mcp_url",
                f"https://mcp.tavily.com/mcp/?tavilyApiKey={self.tavily_api_key}",
            )

        # mlx-lm basic server has no OpenAI tool-calling API
        if self.llm_backend == "mlx" and os.getenv("LLM_ENABLE_TOOLS") is None:
            object.__setattr__(self, "llm_enable_tools", False)

    @property
    def use_tool_calling(self) -> bool:
        return self.llm_enable_tools and self.llm_backend not in ("mlx",)


settings = Settings()
