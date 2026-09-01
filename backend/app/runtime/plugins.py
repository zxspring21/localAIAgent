"""Plugin packs: Claude-style skills + hooks (Hermes-compatible skill folders)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.runtime.hooks import load_hooks_from_file

logger = logging.getLogger(__name__)

_PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins"
_LOADED: list[dict[str, Any]] = []


def plugin_root() -> Path:
    return _PLUGIN_ROOT


def list_plugins() -> list[dict[str, Any]]:
    return list(_LOADED)


def plugin_prompt_block() -> str:
    parts: list[str] = []
    for p in _LOADED:
        md = Path(p["path"]) / "SKILL.md"
        if md.exists():
            parts.append(f"### Plugin {p['name']}\n{md.read_text(encoding='utf-8')[:2000]}")
    return "\n\n".join(parts)


def load_plugins(root: Path | None = None) -> int:
    """Scan plugins/*/plugin.json and register hooks + skill docs."""
    global _LOADED
    _LOADED = []
    base = root or _PLUGIN_ROOT
    if not base.exists():
        logger.info("No plugins directory at %s", base)
        return 0

    count = 0
    for manifest in sorted(base.glob("*/plugin.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Skip plugin %s: %s", manifest, e)
            continue
        name = data.get("name") or manifest.parent.name
        hooks_file = manifest.parent / (data.get("hooks") or "hooks.json")
        hook_count = load_hooks_from_file(hooks_file)
        skill_md = manifest.parent / (data.get("skill") or "SKILL.md")
        _LOADED.append(
            {
                "name": name,
                "version": data.get("version", "0.0.0"),
                "description": data.get("description", ""),
                "path": str(manifest.parent),
                "hooks_loaded": hook_count,
                "skill_doc": skill_md.exists(),
            }
        )
        count += 1
        logger.info("Loaded plugin %s v%s", name, data.get("version"))
    return count
