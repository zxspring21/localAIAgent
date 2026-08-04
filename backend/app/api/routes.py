import json
import logging
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.swarm import run_swarm
from app.auth.jwt import authenticate_user, create_access_token, get_current_user, register_user
from app.automation.scheduler import create_scheduled_task, remove_scheduled_job
from app.brain.controller import brain
from app.config import settings
from app.memory import lt_memory, st_memory
from app.models.database import Session, User, get_db
from app.models.schemas import (
    AsyncChatResponse,
    AsyncTaskStatus,
    ChatRequest,
    ChatResponse,
    MessageResponse,
    ModelInfo,
    ScheduleSkillRequest,
    ScheduleSkillResponse,
    SessionCreate,
    SessionResponse,
    SkillExecuteRequest,
    SkillExecuteResponse,
    SkillInfo,
    SkillTaskStatus,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.skills.registry import list_skills
from app.tasks.chat import execute_skill_task, process_chat_task

logger = logging.getLogger(__name__)
router = APIRouter()


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/auth/register", response_model=UserResponse)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    user = await register_user(db, body.username, body.password, body.email)
    return user


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, body.username, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token)


@router.get("/auth/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/models", response_model=list[ModelInfo])
async def get_models(current_user: User = Depends(get_current_user)):
    models = await brain.list_models()
    return [ModelInfo(**m) for m in models]


@router.get("/skills", response_model=list[SkillInfo])
async def get_skills(current_user: User = Depends(get_current_user)):
    return [SkillInfo(**s) for s in list_skills()]


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    body: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = Session(
        user_id=current_user.id,
        title=body.title,
        model_name=body.model_name or settings.llm_default_model,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Session).where(Session.user_id == current_user.id).order_by(Session.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_session_messages(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    messages = await lt_memory.get_session_messages(db, session_id)
    return messages


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == current_user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await st_memory.clear(str(session_id))
    await db.delete(session)
    await db.commit()
    return {"status": "deleted"}


async def _validate_session(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID) -> Session:
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _validate_session(db, request.session_id, current_user.id)
    model_name = request.model_name or session.model_name

    try:
        if request.use_swarm:
            swarm_result = await run_swarm(
                db=db,
                user_id=current_user.id,
                session_id=request.session_id,
                model_id=model_name,
                user_input=request.message,
            )
            process_result = type("R", (), {
                "content": swarm_result.content,
                "model_name": swarm_result.model_name,
                "tool_calls_made": swarm_result.tool_calls_made,
                "agents_used": swarm_result.agents_used,
            })()
        else:
            process_result = await brain.process_request(
                db=db,
                user_id=current_user.id,
                session_id=request.session_id,
                model_name=model_name,
                user_input=request.message,
                attachments=request.attachments or None,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing error: {e}")

    if request.message:
        session.title = request.message[:80]
        await db.commit()

    return ChatResponse(
        response=process_result.content,
        session_id=request.session_id,
        model_name=process_result.model_name,
        tool_calls_made=process_result.tool_calls_made,
        agents_used=getattr(process_result, "agents_used", []),
    )


@router.post("/uploads")
async def upload_files(
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
):
    from pathlib import Path

    upload_dir = Path("uploads") / str(current_user.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for f in files:
        dest = upload_dir / f.filename
        content = await f.read()
        if len(content) > 5_000_000:
            raise HTTPException(status_code=400, detail=f"File too large: {f.filename}")
        dest.write_bytes(content)
        saved.append(str(dest))
    return {"files": saved, "count": len(saved)}


@router.get("/mcp/status")
async def mcp_status(current_user: User = Depends(get_current_user)):
    from app.mcp.loader import register_mcp_skills
    from app.skills.registry import SKILL_REGISTRY

    count = await register_mcp_skills()
    mcp_tools = [k for k in SKILL_REGISTRY if k.startswith("mcp_")]
    return {
        "mcp_tools_registered": len(mcp_tools),
        "tools": mcp_tools,
        "tavily_mcp": bool(settings.tavily_mcp_url or settings.tavily_api_key),
    }


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _validate_session(db, request.session_id, current_user.id)
    model_name = request.model_name or session.model_name

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in brain.process_request_stream(
                db=db,
                user_id=current_user.id,
                session_id=request.session_id,
                model_name=model_name,
                user_input=request.message,
                attachments=request.attachments or None,
            ):
                yield _format_sse(event["event"], event["data"])

            if request.message:
                session.title = request.message[:80]
                await db.commit()
        except Exception as e:
            logger.exception("Stream error")
            yield _format_sse("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/async", response_model=AsyncChatResponse)
async def chat_async(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _validate_session(db, request.session_id, current_user.id)
    model_name = request.model_name or session.model_name

    task = process_chat_task.delay(
        str(current_user.id),
        str(request.session_id),
        model_name,
        request.message,
    )

    return AsyncChatResponse(task_id=task.id, status="pending")


@router.get("/chat/async/{task_id}", response_model=AsyncTaskStatus)
async def chat_async_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    return _get_celery_task_status(task_id)


def _get_celery_task_status(task_id: str) -> AsyncTaskStatus:
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=process_chat_task.app)
    response = AsyncTaskStatus(task_id=task_id, status=result.status)

    if result.ready():
        if result.successful():
            data = result.result
            if isinstance(data, dict) and data.get("status") == "error":
                response.status = "FAILURE"
                response.error = data.get("message")
            else:
                response.status = "SUCCESS"
                response.result = data
        else:
            response.status = "FAILURE"
            response.error = str(result.result)

    return response


@router.post("/skills/execute-async", response_model=SkillExecuteResponse)
async def execute_skill_async(
    body: SkillExecuteRequest,
    current_user: User = Depends(get_current_user),
):
    task = execute_skill_task.delay(body.skill_name, body.args)
    return SkillExecuteResponse(task_id=task.id, status="pending")


@router.get("/skills/execute-async/{task_id}", response_model=SkillTaskStatus)
async def execute_skill_async_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=execute_skill_task.app)
    response = SkillTaskStatus(task_id=task_id, status=result.status)

    if result.ready():
        if result.successful():
            response.status = "SUCCESS"
            response.result = result.result
        else:
            response.status = "FAILURE"
            response.error = str(result.result)

    return response


@router.post("/automation/schedule-skill", response_model=ScheduleSkillResponse)
async def schedule_skill(
    body: ScheduleSkillRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await create_scheduled_task(
        db=db,
        user_id=current_user.id,
        skill_name=body.skill_name,
        interval_minutes=body.interval_minutes,
        args=body.args,
    )
    return ScheduleSkillResponse(
        task_id=task.id,
        status="success",
        message=f"Skill '{body.skill_name}' scheduled every {body.interval_minutes} minutes.",
    )


@router.delete("/automation/tasks/{task_id}")
async def cancel_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.database import ScheduledTask

    result = await db.execute(
        select(ScheduledTask).where(ScheduledTask.id == task_id, ScheduledTask.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.is_active = False
    remove_scheduled_job(task_id)
    await db.commit()
    return {"status": "cancelled"}
