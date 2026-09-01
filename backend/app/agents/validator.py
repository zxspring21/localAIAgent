"""Answer validation: cross-check draft against RAG sources and web search."""

import json
import logging
import re
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from app.config import settings
from app.llm.router import attach_generation_extras
from app.memory.manager import MemoryContext
from app.skills.registry import execute_skill

logger = logging.getLogger(__name__)

FACTUAL_PATTERNS = re.compile(
    r"\b(20\d{2}|today|latest|current|price|news|who is|when did|how many|percent|%)\b",
    re.I,
)


@dataclass
class ValidationResult:
    valid: bool
    revised_answer: str
    issues: list[str] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    agents_used: list[str] = field(default_factory=lambda: ["validator"])

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "issues": self.issues,
            "sources_used": self.sources_used,
            "agents_used": self.agents_used,
        }


def _needs_web_verification(user_input: str, draft: str) -> bool:
    if not settings.validation_use_web_search:
        return False
    combined = f"{user_input} {draft}"
    return bool(FACTUAL_PATTERNS.search(combined))


def _format_rag_evidence(mem_ctx: MemoryContext) -> str:
    if not mem_ctx.rag_chunks:
        return "No RAG documents retrieved."
    parts = []
    for i, c in enumerate(mem_ctx.rag_chunks[:5], 1):
        parts.append(f"[Doc {i}: {c.get('filename', '?')}]\n{c.get('content', '')[:600]}")
    return "\n\n".join(parts)


async def validate_answer(
    client: AsyncOpenAI,
    api_model: str,
    user_input: str,
    draft_answer: str,
    mem_ctx: MemoryContext,
    spec=None,
) -> ValidationResult:
    """Verify draft answer against RAG + optional web search; revise if needed."""
    if not settings.answer_validation_enabled:
        return ValidationResult(valid=True, revised_answer=draft_answer)

    if not draft_answer or len(draft_answer.strip()) < 10:
        return ValidationResult(valid=True, revised_answer=draft_answer)

    sources_used: list[str] = []
    web_evidence = ""

    if mem_ctx.rag_chunks:
        sources_used.append("rag")

    if _needs_web_verification(user_input, draft_answer):
        try:
            web_evidence = execute_skill("web_search", {"query": user_input[:220]})
            if web_evidence and "error" not in web_evidence.lower()[:80]:
                sources_used.append("web_search")
        except Exception as e:
            logger.warning("Web search for validation failed: %s", e)
            web_evidence = f"(web search unavailable: {e})"

    rag_evidence = _format_rag_evidence(mem_ctx)

    prompt = f"""You are a fact-checking validator agent. Review the draft answer against available evidence.

## User question
{user_input}

## Draft answer
{draft_answer}

## RAG document evidence
{rag_evidence}

## Web search evidence
{web_evidence[:2500] if web_evidence else "Not used."}

## Task
1. Check if the draft contradicts RAG or web evidence
2. Flag unsupported factual claims about dates, numbers, or current events
3. If issues found, provide a corrected answer using only supported evidence
4. If no issues, return the draft unchanged

Respond with JSON only:
{{"valid": true/false, "issues": ["..."], "revised_answer": "final answer text"}}"""

    try:
        kwargs = {
            "model": api_model,
            "messages": [
                {"role": "system", "content": "You are a precise validator. Output JSON only."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": min(settings.llm_max_tokens, 1024),
            "temperature": 0.2,
            "frequency_penalty": settings.llm_frequency_penalty,
            "presence_penalty": settings.llm_presence_penalty,
        }
        if spec is not None:
            kwargs = attach_generation_extras(kwargs, spec)
        resp = await client.chat.completions.create(**kwargs)
        raw = resp.choices[0].message.content or "{}"
        start = raw.find("{")
        end = raw.rfind("}") + 1
        data = json.loads(raw[start:end]) if start >= 0 else {}

        valid = bool(data.get("valid", True))
        issues = data.get("issues") or []
        revised = data.get("revised_answer") or draft_answer

        if not valid and revised == draft_answer and issues:
            revised = _safe_fallback(draft_answer, issues, rag_evidence, web_evidence)

        return ValidationResult(
            valid=valid,
            revised_answer=revised.strip() or draft_answer,
            issues=issues if isinstance(issues, list) else [str(issues)],
            sources_used=sources_used,
        )
    except Exception as e:
        logger.warning("Validation LLM call failed: %s", e)
        return ValidationResult(
            valid=True,
            revised_answer=draft_answer,
            issues=[f"validation_skipped: {e}"],
        )


def _safe_fallback(draft: str, issues: list, rag: str, web: str) -> str:
    """When validator flags issues but gives no revision, append a caution note."""
    note = "\n\n---\n*Note: Some claims could not be fully verified against available sources.*"
    if issues:
        note += "\n*Issues flagged:* " + "; ".join(str(i) for i in issues[:3])
    return draft.rstrip() + note
