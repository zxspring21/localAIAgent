import logging
import uuid
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import ScheduledTask, async_session_factory
from app.skills.registry import execute_skill

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_scheduled_skill(task_id: uuid.UUID):
    async with async_session_factory() as db:
        result = await db.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))
        task = result.scalar_one_or_none()
        if not task or not task.is_active:
            return

        logger.info("Running scheduled skill '%s' for user %s", task.skill_name, task.user_id)
        output = execute_skill(task.skill_name, task.args or {})
        logger.info("Scheduled skill output: %s", output[:200])

        task.last_run_at = datetime.now(timezone.utc)
        task.next_run_at = task.last_run_at + timedelta(minutes=task.interval_minutes)
        await db.commit()


def add_scheduled_job(task_id: uuid.UUID, interval_minutes: int):
    scheduler.add_job(
        _run_scheduled_skill,
        "interval",
        minutes=interval_minutes,
        id=str(task_id),
        args=[task_id],
        replace_existing=True,
    )


def remove_scheduled_job(task_id: uuid.UUID):
    job_id = str(task_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


async def create_scheduled_task(
    db: AsyncSession,
    user_id: uuid.UUID,
    skill_name: str,
    interval_minutes: int,
    args: dict | None = None,
) -> ScheduledTask:
    now = datetime.now(timezone.utc)
    task = ScheduledTask(
        user_id=user_id,
        skill_name=skill_name,
        interval_minutes=interval_minutes,
        args=args or {},
        next_run_at=now + timedelta(minutes=interval_minutes),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    add_scheduled_job(task.id, interval_minutes)
    return task


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("Automation scheduler started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Automation scheduler stopped")
