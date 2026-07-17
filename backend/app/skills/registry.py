import inspect
import json
from collections.abc import Callable
from functools import wraps
from typing import Any, get_type_hints


SKILL_REGISTRY: dict[str, dict[str, Any]] = {}


def _python_type_to_json_schema(py_type: type) -> dict[str, str]:
    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    return {"type": mapping.get(py_type, "string")}


def _build_parameters(func: Callable) -> dict[str, Any]:
    hints = get_type_hints(func)
    sig = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        py_type = hints.get(name, str)
        properties[name] = _python_type_to_json_schema(py_type)
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {"type": "object", "properties": properties, "required": required}


def skill(name: str, description: str):
    def decorator(func: Callable):
        SKILL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "function": func,
            "parameters": _build_parameters(func),
        }

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


def get_skills_definition() -> list[dict[str, Any]]:
    tools = []
    for info in SKILL_REGISTRY.values():
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": info["name"],
                    "description": info["description"],
                    "parameters": info["parameters"],
                },
            }
        )
    return tools


def execute_skill(name: str, arguments: dict[str, Any]) -> str:
    if name not in SKILL_REGISTRY:
        return f"Error: Skill '{name}' not found."

    try:
        result = SKILL_REGISTRY[name]["function"](**arguments)
        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=False, indent=2)
        return str(result)
    except Exception as e:
        return f"Error executing skill '{name}': {e}"


def list_skills() -> list[dict[str, str]]:
    return [{"name": info["name"], "description": info["description"]} for info in SKILL_REGISTRY.values()]
