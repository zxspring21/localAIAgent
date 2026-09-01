"""Claude-style event hooks: PreToolUse, PostToolUse, AgentStart, AgentComplete."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

HOOK_EVENTS = ("AgentStart", "PreToolUse", "PostToolUse", "AgentComplete")

HookFn = Callable[[dict[str, Any]], dict[str, Any] | None]


@dataclass
class HookResult:
    blocked: bool = False
    message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


_HOOKS: dict[str, list[HookFn]] = {name: [] for name in HOOK_EVENTS}


def register_hook(event: str, fn: HookFn) -> None:
    if event not in _HOOKS:
        raise ValueError(f"Unknown hook event: {event}")
    _HOOKS[event].append(fn)


def fire_hook(event: str, payload: dict[str, Any]) -> HookResult:
    result = HookResult()
    for fn in _HOOKS.get(event, []):
        try:
            out = fn(payload) or {}
        except Exception as e:
            logger.warning("Hook %s failed: %s", event, e)
            continue
        if out.get("block"):
            result.blocked = True
            result.message = str(out.get("message") or "Blocked by hook")
            return result
        result.extra.update({k: v for k, v in out.items() if k not in ("block", "message")})
    return result


def load_hooks_from_file(path: Path) -> int:
    """Load declarative hooks.json: { "PreToolUse": [{ "deny_skills": [...] }] }."""
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    deny = data.get("PreToolUse", [])
    if isinstance(deny, list):
        blocked_skills: set[str] = set()
        for item in deny:
            if isinstance(item, dict):
                blocked_skills.update(item.get("deny_skills") or [])
        if blocked_skills:

            def _deny(payload: dict[str, Any], skills=blocked_skills) -> dict:
                name = payload.get("skill") or payload.get("name")
                if name in skills:
                    return {"block": True, "message": f"Hook denied skill '{name}'"}
                return {}

            register_hook("PreToolUse", _deny)
            count += 1
    return count


def reset_hooks_for_tests() -> None:
    for key in _HOOKS:
        _HOOKS[key] = []
