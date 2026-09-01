"""Per-run sandbox. Always torn down when the agent loop finishes."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from app.config import settings
from app.runtime.hooks import fire_hook

logger = logging.getLogger(__name__)

_current: ContextVar["AgentSandbox | None"] = ContextVar("agent_sandbox", default=None)


@dataclass
class AgentSandbox:
    run_id: str
    user_id: str
    session_id: str
    kind: str
    workdir: Path
    active: bool = True
    extra: dict = field(default_factory=dict)

    def teardown(self) -> None:
        if not self.active:
            return
        fire_hook(
            "AgentComplete",
            {
                "run_id": self.run_id,
                "user_id": self.user_id,
                "session_id": self.session_id,
                "kind": self.kind,
                "workdir": str(self.workdir),
            },
        )
        isolated = self.extra.get("isolated", True)
        if isolated:
            try:
                shutil.rmtree(self.workdir, ignore_errors=True)
            except Exception as e:
                logger.warning("Sandbox teardown failed: %s", e)
        self.active = False
        logger.info("Sandbox ended run_id=%s kind=%s", self.run_id, self.kind)


def current_sandbox() -> AgentSandbox | None:
    return _current.get()


def sandbox_workdir() -> Path:
    box = current_sandbox()
    if box and box.active:
        return box.workdir
    return Path.cwd()


def resolve_in_sandbox(file_path: str) -> Path:
    """Resolve a path inside the current run sandbox (or cwd if none)."""
    root = sandbox_workdir().resolve()
    path = Path(file_path)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not str(path).startswith(str(root)):
        raise PermissionError("Path is outside the agent sandbox")
    return path


@asynccontextmanager
async def agent_run_sandbox(
    user_id: str | uuid.UUID,
    session_id: str | uuid.UUID,
    kind: str = "chat",
) -> AsyncIterator[AgentSandbox]:
    run_id = str(uuid.uuid4())
    if settings.sandbox_enabled:
        root = Path(os.getenv("AGENT_SANDBOX_ROOT") or tempfile.gettempdir()) / "localai-sandboxes"
        root.mkdir(parents=True, exist_ok=True)
        workdir = Path(tempfile.mkdtemp(prefix=f"{kind}-{run_id[:8]}-", dir=root))
    else:
        workdir = Path.cwd()

    box = AgentSandbox(
        run_id=run_id,
        user_id=str(user_id),
        session_id=str(session_id),
        kind=kind,
        workdir=workdir,
        extra={"isolated": settings.sandbox_enabled},
    )
    token = _current.set(box)
    fire_hook(
        "AgentStart",
        {
            "run_id": run_id,
            "user_id": str(user_id),
            "session_id": str(session_id),
            "kind": kind,
            "workdir": str(workdir),
        },
    )
    logger.info("Sandbox started run_id=%s kind=%s dir=%s isolated=%s", run_id, kind, workdir, settings.sandbox_enabled)
    try:
        yield box
    finally:
        box.teardown()
        _current.reset(token)
