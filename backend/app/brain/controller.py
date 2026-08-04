import json
import logging
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.llm.registry import catalog_to_api_dict, list_catalog_models
from app.llm.router import get_api_model_id, get_llm_client, use_tools_for_model, validate_model
from app.memory import lt_memory, st_memory
from app.skills.registry import execute_skill, get_skills_definition

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are a powerful Multi-Agent AI Assistant with access to various tools and skills.

## Your Capabilities
- Chain-of-Thought reasoning: think step-by-step before acting
- Tool use: call available skills when needed to accomplish tasks
- Memory: you have access to relevant past conversation context
- Web search via Tavily for up-to-date information beyond your training cutoff

## Relevant Long-Term Memory
{lt_memories}

## Guidelines
1. Analyze the user's request carefully before responding
2. Use web_search or MCP tools when you need current information (news, prices, events after 2023)
3. After tool execution, synthesize results into a clear, helpful response
4. Be concise but thorough
5. If a task requires multiple steps, break it down and execute sequentially
"""

MLX_SYSTEM_PROMPT_TEMPLATE = """You are a helpful AI Assistant running locally on Apple Silicon via MLX.

## Relevant Long-Term Memory
{lt_memories}

## Guidelines
1. Answer clearly and concisely in the user's language
2. Think step-by-step for complex questions
3. Your knowledge may be outdated — for current events say you may not have latest data
4. If you are unsure, say so honestly
"""


@dataclass
class ProcessResult:
    content: str
    model_name: str
    tool_calls_made: list[str] = field(default_factory=list)
    iterations: int = 0
    agents_used: list[str] = field(default_factory=list)


class CoreController:
    def __init__(self, llm_url: str | None = None):
        self.llm_client = AsyncOpenAI(
            base_url=llm_url or settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout,
        )
        self.vllm_client = self.llm_client

    async def check_llm_health(self) -> tuple[bool, str]:
        base = settings.llm_base_url.replace("/v1", "")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{base}/v1/models")
                if resp.status_code == 200:
                    return True, f"{settings.llm_backend} reachable at {settings.llm_base_url}"
                return False, f"LLM returned HTTP {resp.status_code}"
        except Exception as e:
            hint = "./scripts/start_llm_mlx.sh" if settings.llm_backend == "mlx" else "./scripts/start_vllm.sh"
            return False, f"LLM unreachable ({e}). Start with: {hint}"

    def _completion_kwargs(
        self,
        api_model: str,
        messages: list,
        spec,
        stream: bool = False,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": api_model,
            "messages": messages,
            "max_tokens": settings.llm_max_tokens,
            "temperature": 0.7,
        }
        if stream:
            kwargs["stream"] = True

        if use_tools_for_model(spec):
            tools = get_skills_definition()
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

        return kwargs

    async def _build_messages(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        user_input: str,
        spec,
        attachments: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        st_history = await st_memory.get_history(str(session_id))
        lt_memories = await lt_memory.retrieve(user_id, user_input)
        template = MLX_SYSTEM_PROMPT_TEMPLATE if spec.backend == "mlx" else SYSTEM_PROMPT_TEMPLATE
        system_prompt = template.format(
            lt_memories=json.dumps(lt_memories, ensure_ascii=False, indent=2) if lt_memories else "None"
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(st_history)

        user_content = user_input
        if attachments:
            user_content += "\n\n[Attached files]\n" + "\n".join(f"- {f}" for f in attachments)

        messages.append({"role": "user", "content": user_content})
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
        attachments: list[str] | None = None,
    ) -> ProcessResult:
        spec, api_model = validate_model(model_name)
        client = get_llm_client(spec)

        logger.info(
            "Processing backend=%s model=%s api_model=%s user=%s",
            spec.backend,
            spec.id,
            api_model,
            user_id,
        )

        if spec.backend == "mlx":
            ok, msg = await self.check_llm_health()
            if not ok:
                raise RuntimeError(msg)

        messages = await self._build_messages(user_id, session_id, user_input, spec, attachments)
        tool_calls_made: list[str] = []
        final_content = ""
        iterations = 0

        try:
            for iteration in range(settings.max_cot_iterations):
                iterations = iteration + 1
                response = await client.chat.completions.create(
                    **self._completion_kwargs(api_model, messages, spec),
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
                final_content = messages[-1].get("content", "Max iterations reached.")
        except (APIConnectionError, APITimeoutError) as e:
            raise RuntimeError(
                f"Cannot reach LLM ({spec.display_name}). "
                f"Local MLX: ./scripts/start_llm_mlx.sh — {e}"
            ) from e

        await self._save_messages(db, session_id, user_id, user_input, final_content)

        return ProcessResult(
            content=final_content,
            model_name=spec.id,
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
        attachments: list[str] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        try:
            spec, api_model = validate_model(model_name)
            client = get_llm_client(spec)
        except RuntimeError as e:
            yield {"event": "error", "data": {"message": str(e)}}
            return

        if spec.backend == "mlx":
            ok, msg = await self.check_llm_health()
            if not ok:
                yield {"event": "error", "data": {"message": msg}}
                return

        messages = await self._build_messages(user_id, session_id, user_input, spec, attachments)
        tool_calls_made: list[str] = []
        final_content = ""

        yield {"event": "start", "data": {"session_id": str(session_id), "model": spec.id, "api_model": api_model}}

        try:
            for iteration in range(settings.max_cot_iterations):
                if iteration > 0:
                    yield {"event": "thinking", "data": {"iteration": iteration + 1}}

                stream = await client.chat.completions.create(
                    **self._completion_kwargs(api_model, messages, spec, stream=True),
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
                        yield {"event": "tool_start", "data": {"name": function_name, "args": function_args}}
                        observation = execute_skill(function_name, function_args)
                        yield {"event": "tool_result", "data": {"name": function_name, "result": observation[:500]}}
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
                final_content = "Max iterations reached."
                yield {"event": "token", "data": {"content": final_content}}
        except (APIConnectionError, APITimeoutError) as e:
            yield {"event": "error", "data": {"message": f"LLM connection failed: {e}"}}
            return
        except Exception as e:
            yield {"event": "error", "data": {"message": str(e)}}
            return

        await self._save_messages(db, session_id, user_id, user_input, final_content)

        yield {
            "event": "done",
            "data": {
                "session_id": str(session_id),
                "model_name": spec.id,
                "tool_calls_made": tool_calls_made,
                "content": final_content,
            },
        }

    async def list_models(self) -> list[dict]:
        """Return catalog models with availability flags."""
        return [catalog_to_api_dict(m) for m in list_catalog_models(include_unavailable=True)]


brain = CoreController()
