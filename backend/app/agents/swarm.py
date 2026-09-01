"""Multi-agent swarm: planner → sub-agents → synthesizer."""

import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.agents.validator import validate_answer
from app.llm.router import attach_generation_extras, get_llm_client, validate_model
from app.memory import memory_manager
from app.runtime.sandbox import agent_run_sandbox
from app.skills.registry import execute_skill

from .swarm_types import SUB_AGENT_ROLES, SwarmResult

logger = logging.getLogger(__name__)


async def run_swarm(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    model_id: str,
    user_input: str,
) -> SwarmResult:
    async with agent_run_sandbox(user_id, session_id, "swarm"):
        return await _run_swarm_body(db, user_id, session_id, model_id, user_input)


async def _run_swarm_body(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    model_id: str,
    user_input: str,
) -> SwarmResult:
    spec, api_model = validate_model(model_id)
    client = get_llm_client(spec)
    agents_used: list[str] = []
    tool_calls: list[str] = []

    mem_ctx = await memory_manager.build_context(user_id, session_id, user_input)
    memory_block = ""
    if mem_ctx.lt_memories:
        memory_block += f"\n\nPast context:\n{json.dumps(mem_ctx.lt_memories, ensure_ascii=False)[:1500]}"
    if mem_ctx.rag_chunks:
        rag_text = "\n".join(c.get("content", "")[:400] for c in mem_ctx.rag_chunks[:3])
        memory_block += f"\n\nRelevant documents:\n{rag_text}"

    plan_kwargs = attach_generation_extras(
        {
            "model": api_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a task planner. Break the user request into 1-3 subtasks. "
                        "Return JSON: {\"subtasks\": [{\"agent\": \"researcher|analyst|executor\", "
                        "\"task\": \"description\"}]}"
                    ),
                },
                {"role": "user", "content": user_input + memory_block},
            ],
            "max_tokens": 512,
            "temperature": 0.3,
        },
        spec,
    )
    plan_resp = await client.chat.completions.create(**plan_kwargs)
    plan_text = plan_resp.choices[0].message.content or "{}"
    agents_used.append("planner")

    try:
        start = plan_text.find("{")
        end = plan_text.rfind("}") + 1
        plan = json.loads(plan_text[start:end]) if start >= 0 else {"subtasks": []}
        subtasks = plan.get("subtasks", [])[: settings.max_swarm_agents]
    except json.JSONDecodeError:
        subtasks = [{"agent": "researcher", "task": user_input}]

    if not subtasks:
        subtasks = [{"agent": "researcher", "task": user_input}]

    observations: list[str] = []
    for sub in subtasks:
        agent_name = sub.get("agent", "researcher")
        task = sub.get("task", user_input)
        role = next((r for r in SUB_AGENT_ROLES if r["name"] == agent_name), SUB_AGENT_ROLES[0])
        agents_used.append(agent_name)

        agent_kwargs = attach_generation_extras(
            {
                "model": api_model,
                "messages": [
                    {"role": "system", "content": f"You are the {agent_name} sub-agent. {role['description']}"},
                    {"role": "user", "content": task},
                ],
                "max_tokens": settings.llm_max_tokens,
                "temperature": 0.5,
            },
            spec,
        )
        agent_resp = await client.chat.completions.create(**agent_kwargs)
        agent_output = agent_resp.choices[0].message.content or ""

        if agent_name == "researcher" or "search" in task.lower():
            for tool in role.get("tools", []):
                if tool.startswith("mcp_") or tool == "web_search":
                    try:
                        args = {"query": task[:200]} if tool == "web_search" else {"query": task[:200]}
                        search_result = execute_skill(tool, args)
                        tool_calls.append(tool)
                        agent_output += f"\n\n[{tool}]\n{search_result[:1500]}"
                        break
                    except Exception as e:
                        logger.warning("Swarm tool %s failed: %s", tool, e)
            else:
                search_result = execute_skill("web_search", {"query": task[:200]})
                tool_calls.append("web_search")
                agent_output += f"\n\n[Web Search Results]\n{search_result[:1500]}"

        observations.append(f"### {agent_name.upper()}\nTask: {task}\n\n{agent_output}")

    synth_kwargs = attach_generation_extras(
        {
            "model": api_model,
            "messages": [
                {
                    "role": "system",
                    "content": "Synthesize sub-agent results into one clear, complete answer for the user.",
                },
                {
                    "role": "user",
                    "content": f"Original request: {user_input}\n\nSub-agent outputs:\n" + "\n\n".join(observations),
                },
            ],
            "max_tokens": settings.llm_max_tokens,
            "temperature": 0.6,
        },
        spec,
    )
    synth_resp = await client.chat.completions.create(**synth_kwargs)
    final = synth_resp.choices[0].message.content or "No response generated."
    agents_used.append("synthesizer")

    validation = await validate_answer(
        client, api_model, user_input, final, mem_ctx, spec
    )
    if validation.agents_used:
        agents_used.extend(validation.agents_used)
    final = validation.revised_answer

    await memory_manager.save_turn(db, session_id, user_id, user_input, final)

    return SwarmResult(
        content=final,
        model_name=spec.id,
        agents_used=agents_used,
        tool_calls_made=tool_calls,
        validation=validation.to_dict(),
    )
