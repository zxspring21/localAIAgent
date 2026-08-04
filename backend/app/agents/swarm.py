"""Multi-agent swarm: planner → sub-agents → synthesizer (Kimi-style)."""

import json
import logging
import uuid
from dataclasses import dataclass, field

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.llm.router import get_api_model_id, get_llm_client, validate_model
from app.skills.registry import execute_skill

logger = logging.getLogger(__name__)

SUB_AGENT_ROLES = [
    {
        "name": "researcher",
        "description": "Search the web and gather current facts",
        "tools": ["web_search", "mcp_tavily_tavily_search"],
    },
    {
        "name": "analyst",
        "description": "Analyze data and break down complex problems",
        "tools": ["read_file", "list_directory"],
    },
    {
        "name": "executor",
        "description": "Run commands and write files to accomplish tasks",
        "tools": ["execute_system_command", "write_file", "run_github_code"],
    },
]


@dataclass
class SwarmResult:
    content: str
    model_name: str
    agents_used: list[str] = field(default_factory=list)
    tool_calls_made: list[str] = field(default_factory=list)


async def run_swarm(
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

    # 1. Planner
    plan_resp = await client.chat.completions.create(
        model=api_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a task planner. Break the user request into 1-3 subtasks. "
                    "Return JSON: {\"subtasks\": [{\"agent\": \"researcher|analyst|executor\", "
                    "\"task\": \"description\"}]}"
                ),
            },
            {"role": "user", "content": user_input},
        ],
        max_tokens=512,
        temperature=0.3,
    )
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

    # 2. Sub-agents
    observations: list[str] = []
    for sub in subtasks:
        agent_name = sub.get("agent", "researcher")
        task = sub.get("task", user_input)
        role = next((r for r in SUB_AGENT_ROLES if r["name"] == agent_name), SUB_AGENT_ROLES[0])
        agents_used.append(agent_name)

        agent_resp = await client.chat.completions.create(
            model=api_model,
            messages=[
                {"role": "system", "content": f"You are the {agent_name} sub-agent. {role['description']}"},
                {"role": "user", "content": task},
            ],
            max_tokens=settings.llm_max_tokens,
            temperature=0.5,
        )
        agent_output = agent_resp.choices[0].message.content or ""

        if agent_name == "researcher" or "search" in task.lower():
            search_result = execute_skill("web_search", {"query": task[:200]})
            tool_calls.append("web_search")
            agent_output += f"\n\n[Web Search Results]\n{search_result[:1500]}"

        observations.append(f"### {agent_name.upper()}\nTask: {task}\n\n{agent_output}")

    # 3. Synthesizer
    synth_resp = await client.chat.completions.create(
        model=api_model,
        messages=[
            {
                "role": "system",
                "content": "Synthesize sub-agent results into one clear, complete answer for the user.",
            },
            {"role": "user", "content": f"Original request: {user_input}\n\nSub-agent outputs:\n" + "\n\n".join(observations)},
        ],
        max_tokens=settings.llm_max_tokens,
        temperature=0.6,
    )
    final = synth_resp.choices[0].message.content or "No response generated."
    agents_used.append("synthesizer")

    return SwarmResult(
        content=final,
        model_name=spec.id,
        agents_used=agents_used,
        tool_calls_made=tool_calls,
    )
