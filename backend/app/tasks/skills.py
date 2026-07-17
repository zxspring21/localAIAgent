import logging

from app.automation.scheduler import _run_scheduled_skill
from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.run_scheduled_skill")
def run_scheduled_skill_task(task_id: str):
    import asyncio
    import uuid

    asyncio.run(_run_scheduled_skill(uuid.UUID(task_id)))
    return {"status": "completed", "task_id": task_id}
