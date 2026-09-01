"""Hermes-style observe → think → act → observe loop.

Works without native OpenAI tool-calling (MLX) by parsing:

    Thought: ...
    Action: skill_name
    Action Input: {...} or free text
    Observation: ...
    Final Answer: ...
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.skills.registry import SKILL_REGISTRY, execute_skill, list_skills

logger = logging.getLogger(__name__)

ACTION_RE = re.compile(
    r"Action:\s*([A-Za-z0-9_\-]+)\s*(?:\n|\r\n)Action Input:\s*(.+?)(?:\n(?:Observation|Thought|Final Answer):|\Z)",
    re.DOTALL | re.IGNORECASE,
)
FINAL_RE = re.compile(r"Final Answer:\s*(.+)\Z", re.DOTALL | re.IGNORECASE)


def hermes_skill_block() -> str:
    lines = [f"- {s['name']}: {s['description']}" for s in list_skills()]
    return "\n".join(lines) if lines else "- (no skills registered)"


def hermes_protocol_prompt() -> str:
    return f"""You follow the Hermes agent protocol. For each step output exactly this format:

Thought: <brief reasoning>
Action: <one skill name from the list>
Action Input: <JSON object or a short string>

After you receive Observation, continue. When you can answer the user, output:

Thought: <reasoning>
Final Answer: <the complete answer for the user>

Never invent Observation. Never repeat the same Action+Input more than once.

## Available skills
{hermes_skill_block()}
"""


@dataclass
class HermesStep:
    thought: str
    action: str | None
    action_input: dict | str | None
    final_answer: str | None


def parse_hermes(text: str) -> HermesStep:
    thought = ""
    m_thought = re.search(r"Thought:\s*(.+?)(?:\n(?:Action|Final Answer):|\Z)", text, re.DOTALL | re.I)
    if m_thought:
        thought = m_thought.group(1).strip()

    final = None
    m_final = FINAL_RE.search(text)
    if m_final:
        final = m_final.group(1).strip()

    action = None
    action_input: dict | str | None = None
    m_act = ACTION_RE.search(text)
    if m_act and not (final and text.lower().rfind("final answer") < text.lower().rfind("action:")):
        # Prefer Final Answer if both exist and Final Answer is last
        action = m_act.group(1).strip()
        raw_in = m_act.group(2).strip()
        action_input = _parse_input(raw_in)

    if final and (not action or text.lower().rfind("final answer") > text.lower().rfind("action:")):
        return HermesStep(thought=thought, action=None, action_input=None, final_answer=final)

    return HermesStep(thought=thought, action=action, action_input=action_input, final_answer=None)


def _parse_input(raw: str) -> dict | str:
    raw = raw.strip().strip("`")
    if raw.startswith("{") and raw.endswith("}"):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"query": str(data)}
        except json.JSONDecodeError:
            pass
    return raw


def skill_args(skill_name: str, action_input: dict | str | None) -> dict:
    if isinstance(action_input, dict):
        return action_input
    info = SKILL_REGISTRY.get(skill_name) or {}
    params = (info.get("parameters") or {}).get("properties") or {}
    required = (info.get("parameters") or {}).get("required") or []
    text = str(action_input or "")
    if "query" in params:
        return {"query": text}
    if required:
        return {required[0]: text}
    if params:
        return {next(iter(params)): text}
    return {"input": text}


def run_hermes_action(step: HermesStep) -> str | None:
    """Execute one Hermes Action. Returns observation text, or None if no action."""
    if not step.action:
        return None
    if step.action not in SKILL_REGISTRY:
        return f"Unknown skill '{step.action}'. Available: {', '.join(SKILL_REGISTRY)}"
    args = skill_args(step.action, step.action_input)
    return execute_skill(step.action, args)


def extract_user_facing_answer(text: str) -> str:
    step = parse_hermes(text)
    if step.final_answer:
        return step.final_answer
    return text
