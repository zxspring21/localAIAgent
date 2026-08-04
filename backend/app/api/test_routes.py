"""Independent functionality tests for each system module."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from qdrant_client import QdrantClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.brain.controller import brain
from app.celery_app import celery_app
from app.config import settings
from app.memory import lt_memory, st_memory
from app.models.database import Session, User, get_db
from app.models.schemas import TestResult, TestSuiteResponse
from app.skills.registry import SKILL_REGISTRY, execute_skill, list_skills
from app.skills.web_search import search_web
from app.tasks.chat import execute_skill_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tests", tags=["tests"])


def _result(name: str, module: str, ok: bool, message: str, details: dict | None = None) -> TestResult:
    return TestResult(
        name=name,
        module=module,
        status="pass" if ok else "fail",
        message=message,
        details=details or {},
        tested_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/overview", response_model=TestSuiteResponse)
async def test_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    results = await asyncio.gather(
        _test_vllm(),
        _test_postgres(db),
        _test_redis(),
        _test_qdrant(),
        _test_skills_registry(),
        _test_web_search(),
        _test_celery(),
        _test_auth(current_user),
        _test_multi_session(db, current_user),
        _test_st_memory(),
        _test_lt_memory(db, current_user),
        _test_automation_scheduler(),
        return_exceptions=True,
    )

    parsed: list[TestResult] = []
    for r in results:
        if isinstance(r, Exception):
            parsed.append(_result("unknown", "system", False, str(r)))
        else:
            parsed.append(r)

    passed = sum(1 for r in parsed if r.status == "pass")
    return TestSuiteResponse(
        total=len(parsed),
        passed=passed,
        failed=len(parsed) - passed,
        results=parsed,
        ports={
            "frontend_ui": settings.frontend_url,
            "backend_api": f"http://localhost:{settings.app_port}",
            "vllm_inference": settings.llm_base_url.replace("/v1", ""),
            "llm_backend": settings.llm_backend,
            "note": f"LLM backend: {settings.llm_backend} at port 8000 — Frontend UI at port 3000",
        },
    )


@router.get("/vllm", response_model=TestResult)
async def test_vllm(current_user: User = Depends(get_current_user)):
    return await _test_vllm()


@router.get("/postgres", response_model=TestResult)
async def test_postgres(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _test_postgres(db)


@router.get("/redis", response_model=TestResult)
async def test_redis(current_user: User = Depends(get_current_user)):
    return await _test_redis()


@router.get("/qdrant", response_model=TestResult)
async def test_qdrant(current_user: User = Depends(get_current_user)):
    return await _test_qdrant()


@router.get("/skills", response_model=TestResult)
async def test_skills(current_user: User = Depends(get_current_user)):
    return await _test_skills_registry()


@router.get("/web-search", response_model=TestResult)
async def test_web_search_endpoint(current_user: User = Depends(get_current_user)):
    return await _test_web_search()


@router.get("/celery", response_model=TestResult)
async def test_celery_endpoint(current_user: User = Depends(get_current_user)):
    return await _test_celery()


@router.get("/auth", response_model=TestResult)
async def test_auth_endpoint(current_user: User = Depends(get_current_user)):
    return await _test_auth(current_user)


@router.get("/multi-session", response_model=TestResult)
async def test_multi_session_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _test_multi_session(db, current_user)


@router.get("/memory-st", response_model=TestResult)
async def test_memory_st(current_user: User = Depends(get_current_user)):
    return await _test_st_memory()


@router.get("/memory-lt", response_model=TestResult)
async def test_memory_lt(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _test_lt_memory(db, current_user)


@router.get("/automation", response_model=TestResult)
async def test_automation(current_user: User = Depends(get_current_user)):
    return await _test_automation_scheduler()


@router.get("/cot-loop", response_model=TestResult)
async def test_cot_loop(current_user: User = Depends(get_current_user)):
    """Verify CoreController CoT loop structure (tools + vLLM client wired)."""
    tools = brain.vllm_client is not None and len(SKILL_REGISTRY) > 0
    models = await brain.list_models()
    return _result(
        name="CoT Loop & Multi-Agent",
        module="brain/controller",
        ok=tools,
        message="CoreController wired with vLLM client and skill registry" if tools else "Missing components",
        details={
            "registered_skills": len(SKILL_REGISTRY),
            "skill_names": list(SKILL_REGISTRY.keys()),
            "vllm_base_url": settings.llm_base_url,
            "max_cot_iterations": settings.max_cot_iterations,
            "models_available": len(models),
            "default_model": settings.llm_default_model,
        },
    )


async def _test_vllm() -> TestResult:
    ok, msg = await brain.check_llm_health()
    models = await brain.list_models()
    has_models = len(models) > 0
    hint = "./scripts/start_llm_mlx.sh" if settings.llm_backend == "mlx" else "./scripts/start_vllm.sh"
    return _result(
        name=f"LLM Connection ({settings.llm_backend})",
        module="LLM Backend",
        ok=ok and has_models,
        message=msg if ok else f"{msg} — run: {hint}",
        details={
            "backend": settings.llm_backend,
            "base_url": settings.llm_base_url,
            "default_model": settings.llm_default_model,
            "models": [m["id"] for m in models],
            "tools_enabled": settings.use_tool_calling,
        },
    )


async def _test_postgres(db: AsyncSession) -> TestResult:
    try:
        result = await db.execute(text("SELECT 1 AS ok"))
        row = result.scalar()
        user_count = await db.execute(text("SELECT COUNT(*) FROM users"))
        count = user_count.scalar()
        return _result(
            name="PostgreSQL",
            module="Memory & Auth (SQL)",
            ok=row == 1,
            message="PostgreSQL connected",
            details={"database_url": settings.database_url.split("@")[-1], "user_count": count},
        )
    except Exception as e:
        return _result("PostgreSQL", "Memory & Auth (SQL)", False, str(e))


async def _test_redis() -> TestResult:
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        pong = await r.ping()
        await r.close()
        return _result(
            name="Redis (ST Memory)",
            module="Short-Term Memory",
            ok=pong is True,
            message="Redis connected for session history cache",
            details={"redis_url": settings.redis_url},
        )
    except Exception as e:
        return _result("Redis (ST Memory)", "Short-Term Memory", False, str(e))


async def _test_qdrant() -> TestResult:
    try:
        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, timeout=5)
        collections = client.get_collections()
        names = [c.name for c in collections.collections]
        has_collection = settings.qdrant_collection in names
        return _result(
            name="Qdrant (LT Memory)",
            module="Long-Term Memory / Vector DB",
            ok=True,
            message=f"Qdrant connected — collection '{settings.qdrant_collection}' {'exists' if has_collection else 'will be created on first write'}",
            details={"host": settings.qdrant_host, "port": settings.qdrant_port, "collections": names},
        )
    except Exception as e:
        return _result("Qdrant (LT Memory)", "Long-Term Memory / Vector DB", False, str(e))


async def _test_skills_registry() -> TestResult:
    skills = list_skills()
    test_out = execute_skill("execute_system_command", {"command": "echo skill_test_ok"})
    ok = len(skills) >= 5 and "skill_test_ok" in test_out
    return _result(
        name="Skill Registry",
        module="Agents & Skills",
        ok=ok,
        message=f"{len(skills)} skills registered, execute_system_command works",
        details={"skills": skills, "test_output": test_out[:200]},
    )


async def _test_web_search() -> TestResult:
    try:
        result = search_web("Python programming language")
        ok = len(result) > 20 and "Web search failed" not in result
        provider = settings.web_search_provider
        if settings.tavily_api_key:
            provider_detail = f"{provider} (Tavily key configured)"
        elif settings.serpapi_api_key:
            provider_detail = f"{provider} (SerpAPI key configured)"
        else:
            provider_detail = f"{provider} (no API keys — using DuckDuckGo)"
        return _result(
            name="Web Search API",
            module="Skills / Web Search",
            ok=ok,
            message=f"Search returned {len(result)} chars via {provider_detail}",
            details={"provider": provider, "preview": result[:300]},
        )
    except Exception as e:
        return _result("Web Search API", "Skills / Web Search", False, str(e))


async def _test_celery() -> TestResult:
    try:
        inspect = celery_app.control.inspect(timeout=3)
        active = inspect.active()
        ping = inspect.ping()
        workers = list(ping.keys()) if ping else []

        if workers:
            task = execute_skill_task.delay("execute_system_command", {"command": "echo celery_ok"})
            result = task.get(timeout=15)
            ok = result.get("status") == "success" and "celery_ok" in result.get("result", "")
            return _result(
                name="Celery Async Tasks",
                module="Automation / Celery",
                ok=ok,
                message=f"Celery worker running — async skill execution OK ({len(workers)} worker(s))",
                details={"workers": workers, "task_result": result},
            )

        return _result(
            name="Celery Async Tasks",
            module="Automation / Celery",
            ok=False,
            message="No Celery workers running — start with: cd backend && celery -A app.celery_app worker",
            details={"broker": settings.celery_broker_url, "active_tasks": active},
        )
    except Exception as e:
        return _result("Celery Async Tasks", "Automation / Celery", False, str(e))


async def _test_auth(user: User) -> TestResult:
    return _result(
        name="JWT Auth (Multi-User)",
        module="Auth",
        ok=user is not None and user.username,
        message=f"Authenticated as '{user.username}' (user_id={user.id})",
        details={"user_id": str(user.id), "username": user.username},
    )


async def _test_multi_session(db: AsyncSession, user: User) -> TestResult:
    try:
        s1 = Session(user_id=user.id, title="Test Session A", model_name=settings.llm_default_model)
        s2 = Session(user_id=user.id, title="Test Session B", model_name=settings.llm_default_model)
        db.add_all([s1, s2])
        await db.flush()

        await st_memory.save_message(str(s1.id), {"role": "user", "content": "session A message"})
        await st_memory.save_message(str(s2.id), {"role": "user", "content": "session B message"})

        hist_a = await st_memory.get_history(str(s1.id))
        hist_b = await st_memory.get_history(str(s2.id))

        isolated = (
            len(hist_a) == 1
            and len(hist_b) == 1
            and hist_a[0]["content"] == "session A message"
            and hist_b[0]["content"] == "session B message"
        )

        await st_memory.clear(str(s1.id))
        await st_memory.clear(str(s2.id))
        await db.delete(s1)
        await db.delete(s2)
        await db.commit()

        return _result(
            name="Multi-Session Isolation",
            module="Sessions / Memory",
            ok=isolated,
            message="Sessions isolated by session_id in Redis" if isolated else "Session isolation failed",
            details={"session_a_msgs": len(hist_a), "session_b_msgs": len(hist_b)},
        )
    except Exception as e:
        await db.rollback()
        return _result("Multi-Session Isolation", "Sessions / Memory", False, str(e))


async def _test_st_memory() -> TestResult:
    test_id = f"test_{uuid.uuid4().hex[:8]}"
    try:
        msg = {"role": "user", "content": "ST memory test"}
        await st_memory.save_message(test_id, msg)
        history = await st_memory.get_history(test_id)
        await st_memory.clear(test_id)
        ok = len(history) == 1 and history[0]["content"] == "ST memory test"
        return _result(
            name="Short-Term Memory (Redis)",
            module="Memory",
            ok=ok,
            message="Redis ST memory read/write OK" if ok else "ST memory test failed",
            details={"max_messages": settings.st_memory_max_messages},
        )
    except Exception as e:
        return _result("Short-Term Memory (Redis)", "Memory", False, str(e))


async def _test_lt_memory(db: AsyncSession, user: User) -> TestResult:
    test_session = Session(user_id=user.id, title="LT Test", model_name=settings.llm_default_model)
    db.add(test_session)
    await db.flush()
    try:
        msg_id = await lt_memory.save_message(
            db, test_session.id, user.id, {"role": "user", "content": "LT memory semantic test query"}
        )
        memories = await lt_memory.retrieve(user.id, "semantic test query", limit=3)
        ok = msg_id is not None
        await db.delete(test_session)
        await db.commit()
        return _result(
            name="Long-Term Memory (PG + Qdrant)",
            module="Memory / Reasoning",
            ok=ok,
            message=f"LT memory saved (id={msg_id}), retrieval returned {len(memories)} result(s)",
            details={"message_id": str(msg_id), "retrieved": len(memories)},
        )
    except Exception as e:
        await db.rollback()
        return _result("Long-Term Memory (PG + Qdrant)", "Memory / Reasoning", False, str(e))


async def _test_automation_scheduler() -> TestResult:
    from app.automation.scheduler import scheduler

    running = scheduler.running
    return _result(
        name="APScheduler Automation",
        module="Automation",
        ok=running,
        message="APScheduler is running" if running else "APScheduler not started",
        details={"running": running},
    )
