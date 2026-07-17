import asyncio
import logging
import uuid

from app.celery_app import celery_app
from app.skills.registry import execute_skill

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.execute_skill", bind=True, max_retries=2)
def execute_skill_task(self, skill_name: str, args: dict) -> dict:
    try:
        result = execute_skill(skill_name, args or {})
        return {"status": "success", "skill_name": skill_name, "result": result}
    except Exception as exc:
        logger.error("Skill task failed: %s", exc)
        raise self.retry(exc=exc, countdown=5)


@celery_app.task(name="tasks.process_chat", bind=True)
def process_chat_task(
    self,
    user_id: str,
    session_id: str,
    model_name: str,
    user_input: str,
) -> dict:
    """Run chat processing asynchronously via Celery."""
    from app.brain.controller import brain
    from app.models.database import async_session_factory

    async def _run():
        async with async_session_factory() as db:
            result = await brain.process_request(
                db=db,
                user_id=uuid.UUID(user_id),
                session_id=uuid.UUID(session_id),
                model_name=model_name,
                user_input=user_input,
            )
            return {
                "content": result.content,
                "model_name": result.model_name,
                "tool_calls_made": result.tool_calls_made,
                "iterations": result.iterations,
            }

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("Chat task failed: %s", exc)
        return {"status": "error", "message": str(exc)}
