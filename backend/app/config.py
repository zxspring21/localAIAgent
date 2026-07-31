from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_secret_key: str = "change-me"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8080

    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_default_model: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    vllm_api_key: str = "vllm_not_needed"

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
    serpapi_api_key: str = ""
    web_search_provider: str = "duckduckgo"

    max_cot_iterations: int = 10
    frontend_url: str = "http://localhost:3000"


settings = Settings()
