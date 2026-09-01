import logging

from sqlalchemy import text

from app.models.database import Base, engine

logger = logging.getLogger(__name__)


async def init_database() -> None:
    """Create tables if they do not exist (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(32) DEFAULT 'email'"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_sub VARCHAR(255)"))
    logger.info("Database schema ready.")


async def check_database_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Database connection failed: %s", e)
        return False
