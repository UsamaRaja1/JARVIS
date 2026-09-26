import inspect
from typing import Any

TOOLS: dict[str, dict[str, Any]] = {}


def register_tool(name, description, schema):
    def decorator(func):
        if not name:
            raise ValueError("Tool name is required")
        if name in TOOLS:
            raise ValueError(f"Tool {name!r} is already registered")

        TOOLS[name] = {
            "name": name,
            "description": description,
            "schema": schema,
            "handler": func,
        }
        return func

    return decorator


def list_registered_tools() -> list[dict[str, Any]]:
    return [{"name": tool["name"], "description": tool["description"], "input_schema": tool["schema"]} for tool in TOOLS.values()]


async def call_registered_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    if name not in TOOLS:
        raise ValueError(f"Tool {name!r} not found")

    arguments = arguments or {}
    result = TOOLS[name]["handler"](**arguments)
    if inspect.isawaitable(result):
        return await result
    return result
