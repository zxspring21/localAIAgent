"""Plugin packs: Claude-style skills + hooks (Hermes-compatible skill folders)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.runtime.hooks import load_hooks_from_file

logger = logging.getLogger(__name__)

_PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins"
_ANTHROPIC_ROOT = Path(__file__).resolve().parents[3] / "skills" / "anthropic"
_VENDOR_ROOT = Path(__file__).resolve().parents[3] / "vendor" / "anthropic-skills" / "skills"
_LOADED: list[dict[str, Any]] = []

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def plugin_root() -> Path:
    return _PLUGIN_ROOT


def list_plugins() -> list[dict[str, Any]]:
    return list(_LOADED)


def get_skill_doc(name: str) -> str | None:
    key = name.strip().lower()
    for p in _LOADED:
        if p["name"].lower() == key:
            md = Path(p["path"]) / "SKILL.md"
            if md.exists():
                return md.read_text(encoding="utf-8")
            return p.get("description") or f"Skill '{name}' has no SKILL.md"
    return None


def plugin_prompt_block() -> str:
    if not _LOADED:
        return ""
    lines = [
        "## Claude / Anthropic skills",
        "Official catalog: https://github.com/anthropics/skills/tree/main/skills",
        "When a task matches a skill below, call `load_skill` with that name, then follow the instructions.",
        "For UI or HTML, emit a fenced ```html document so the user can open Preview and Source.",
        "",
    ]
    for p in _LOADED:
        lines.append(f"- **{p['name']}**: {p.get('description') or ''}")
    return "\n".join(lines)


def _parse_frontmatter(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    m = FRONTMATTER_RE.match(text)
    if not m:
        return meta
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta


def _register_skill_dir(folder: Path, source: str) -> None:
    skill_md = folder / "SKILL.md"
    if not skill_md.exists():
        return
    text = skill_md.read_text(encoding="utf-8")
    meta = _parse_frontmatter(text)
    name = meta.get("name") or folder.name
    description = meta.get("description") or ""
    hooks_file = folder / "hooks.json"
    hook_count = load_hooks_from_file(hooks_file) if hooks_file.exists() else 0
    _LOADED.append(
        {
            "name": name,
            "version": "anthropic" if source == "anthropic" else "0.0.0",
            "description": description,
            "path": str(folder),
            "hooks_loaded": hook_count,
            "skill_doc": True,
            "source": source,
        }
    )


def load_plugins(root: Path | None = None) -> int:
    global _LOADED
    _LOADED = []
    count = 0

    catalog = _ANTHROPIC_ROOT / "catalog.json"
    catalog_names: dict[str, str] = {}
    if catalog.exists():
        try:
            data = json.loads(catalog.read_text(encoding="utf-8"))
            for item in data.get("skills") or []:
                catalog_names[item["name"]] = item.get("description", "")
        except Exception as e:
            logger.warning("Anthropic catalog unreadable: %s", e)

    for base, source in (
        (_VENDOR_ROOT, "anthropic-vendor"),
        (_ANTHROPIC_ROOT, "anthropic"),
        (root or _PLUGIN_ROOT, "plugin"),
    ):
        if not base.exists():
            continue
        if source == "plugin":
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
                description = data.get("description", "")
                if skill_md.exists():
                    description = _parse_frontmatter(skill_md.read_text(encoding="utf-8")).get(
                        "description", description
                    )
                _LOADED.append(
                    {
                        "name": name,
                        "version": data.get("version", "0.0.0"),
                        "description": description,
                        "path": str(manifest.parent),
                        "hooks_loaded": hook_count,
                        "skill_doc": skill_md.exists(),
                        "source": source,
                    }
                )
                count += 1
                logger.info("Loaded plugin %s v%s", name, data.get("version"))
            continue

        for folder in sorted(p for p in base.iterdir() if p.is_dir()):
            if (folder / "SKILL.md").exists():
                _register_skill_dir(folder, source)
                count += 1

    loaded_names = {p["name"] for p in _LOADED}
    for name, desc in catalog_names.items():
        if name not in loaded_names:
            _LOADED.append(
                {
                    "name": name,
                    "version": "catalog",
                    "description": desc,
                    "path": str(_ANTHROPIC_ROOT),
                    "hooks_loaded": 0,
                    "skill_doc": False,
                    "source": "anthropic-catalog",
                    "upstream": f"https://github.com/anthropics/skills/tree/main/skills/{name}",
                }
            )
            count += 1

    logger.info("Loaded %d skill packs", len(_LOADED))
    return count
