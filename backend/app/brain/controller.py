import json
import logging
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.memory import lt_memory, st_memory
from app.skills.registry import execute_skill, get_skills_definition

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are a powerful Multi-Agent AI Assistant with access to various tools and skills.

## Your Capabilities
- Chain-of-Thought reasoning: think step-by-step before acting
- Tool use: call available skills when needed to accomplish tasks
- Memory: you have access to relevant past conversation context

## Relevant Long-Term Memory
{lt_memories}

## Guidelines
1. Analyze the user's request carefully before responding
2. Use tools when you need to perform actions (run code, read files, search, etc.)
3. After tool execution, synthesize results into a clear, helpful response
4. Be concise but thorough
5. If a task requires multiple steps, break it down and execute sequentially
"""


@dataclass
class ProcessResult:
    content: str
    model_name: str
    tool_calls_made: list[str] = field(default_factory=list)
    iterations: int = 0


class CoreController:
    def __init__(self, vllm_url: str | None = None):
        self.vllm_client = AsyncOpenAI(
            base_url=vllm_url or settings.vllm_base_url,
            api_key=settings.vllm_api_key,
        )

    async def _build_messages(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        user_input: str,
    ) -> list[dict[str, Any]]:
        st_history = await st_memory.get_history(str(session_id))
        lt_memories = await lt_memory.retrieve(user_id, user_input)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            lt_memories=json.dumps(lt_memories, ensure_ascii=False, indent=2) if lt_memories else "None"
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(st_history)
        messages.append({"role": "user", "content": user_input})
        return messages

    async def _save_messages(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        user_input: str,
        final_content: str,
    ):
        user_msg = {"role": "user", "content": user_input}
        assistant_msg = {"role": "assistant", "content": final_content}
        await st_memory.save_message(str(session_id), user_msg)
        await st_memory.save_message(str(session_id), assistant_msg)
        await lt_memory.save_message(db, session_id, user_id, user_msg)
        await lt_memory.save_message(db, session_id, user_id, assistant_msg)

    async def process_request(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        model_name: str,
        user_input: str,
    ) -> ProcessResult:
        logger.info("Processing request for user=%s session=%s model=%s", user_id, session_id, model_name)

        messages = await self._build_messages(user_id, session_id, user_input)
        tools = get_skills_definition()
        tool_calls_made: list[str] = []
        final_content = ""
        iterations = 0

        for iteration in range(settings.max_cot_iterations):
            iterations = iteration + 1
            response = await self.vllm_client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
            )

            response_message = response.choices[0].message
            msg_dict: dict[str, Any] = {"role": "assistant", "content": response_message.content or ""}

            if response_message.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in response_message.tool_calls
                ]

            messages.append(msg_dict)

            if not response_message.tool_calls:
                final_content = response_message.content or ""
                break

            logger.info("CoT iteration %d: executing %d tool(s)", iteration + 1, len(response_message.tool_calls))

            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                try:
                    function_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    function_args = {}

                tool_calls_made.append(function_name)
                observation = execute_skill(function_name, function_args)

                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": observation,
                    }
                )
        else:
            final_content = messages[-1].get("content", "Max iterations reached without final response.")

        await self._save_messages(db, session_id, user_id, user_input, final_content)

        return ProcessResult(
            content=final_content,
            model_name=model_name,
            tool_calls_made=tool_calls_made,
            iterations=iterations,
        )

    async def process_request_stream(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        model_name: str,
        user_input: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield SSE event dicts: {event, data}."""
        messages = await self._build_messages(user_id, session_id, user_input)
        tools = get_skills_definition()
        tool_calls_made: list[str] = []
        final_content = ""

        yield {"event": "start", "data": {"session_id": str(session_id), "model": model_name}}

        for iteration in range(settings.max_cot_iterations):
            if iteration > 0:
                yield {"event": "thinking", "data": {"iteration": iteration + 1}}

            stream = await self.vllm_client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                stream=True,
            )

            collected_content = ""
            tool_calls_data: dict[int, dict[str, str]] = {}
            finish_reason = None

            async for chunk in stream:
                choice = chunk.choices[0]
                finish_reason = choice.finish_reason
                delta = choice.delta

                if delta.content:
                    collected_content += delta.content
                    yield {"event": "token", "data": {"content": delta.content}}

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_data[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            tool_calls_data[idx]["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            tool_calls_data[idx]["arguments"] += tc.function.arguments

            if tool_calls_data and finish_reason == "tool_calls":
                msg_dict: dict[str, Any] = {
                    "role": "assistant",
                    "content": collected_content or None,
                    "tool_calls": [
                        {
                            "id": tool_calls_data[i]["id"],
                            "type": "function",
                            "function": {
                                "name": tool_calls_data[i]["name"],
                                "arguments": tool_calls_data[i]["arguments"],
                            },
                        }
                        for i in sorted(tool_calls_data)
                    ],
                }
                messages.append(msg_dict)

                for i in sorted(tool_calls_data):
                    tc = tool_calls_data[i]
                    function_name = tc["name"]
                    try:
                        function_args = json.loads(tc["arguments"])
                    except json.JSONDecodeError:
                        function_args = {}

                    tool_calls_made.append(function_name)
                    yield {
                        "event": "tool_start",
                        "data": {"name": function_name, "args": function_args},
                    }

                    observation = execute_skill(function_name, function_args)
                    yield {
                        "event": "tool_result",
                        "data": {"name": function_name, "result": observation[:500]},
                    }

                    messages.append(
                        {
                            "tool_call_id": tc["id"],
                            "role": "tool",
                            "name": function_name,
                            "content": observation,
                        }
                    )
                continue

            final_content = collected_content
            messages.append({"role": "assistant", "content": final_content})
            break
        else:
            final_content = "Max iterations reached without final response."
            yield {"event": "token", "data": {"content": final_content}}

        await self._save_messages(db, session_id, user_id, user_input, final_content)

        yield {
            "event": "done",
            "data": {
                "session_id": str(session_id),
                "model_name": model_name,
                "tool_calls_made": tool_calls_made,
                "content": final_content,
            },
        }

    async def list_models(self) -> list[dict[str, str]]:
        try:
            models = await self.vllm_client.models.list()
            return [{"id": m.id, "name": m.id} for m in models.data]
        except Exception as e:
            logger.warning("Could not fetch models from vLLM: %s", e)
            return [{"id": settings.vllm_default_model, "name": settings.vllm_default_model}]


brain = CoreController()
