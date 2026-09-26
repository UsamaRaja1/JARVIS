import asyncio
import json
from typing import Any

from src.mcp import tool_impl  # noqa: F401 - importing registers built-in tools
from src.mcp.tools import TOOLS, call_registered_tool, list_registered_tools


class MCPServer:
    def list_tools(self):
        return list_registered_tools()

    def call_tool(self, name: str, args: dict):
        return asyncio.run(self.call_tool_async(name, args))

    async def call_tool_async(self, name: str, args: dict | None = None):
        return await call_registered_tool(name, args)


def _result_to_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, default=str)


def create_protocol_server():
    try:
        import mcp.types as types
        from mcp.server.lowlevel import Server
    except ImportError as exc:
        raise RuntimeError("The official MCP SDK is not installed. Run `pip install mcp` or install from requirements.txt.") from exc

    server = Server("jarvis")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return [types.Tool(name=tool["name"], description=tool["description"], inputSchema=tool["schema"]) for tool in TOOLS.values()]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
        result = await call_registered_tool(name, arguments)
        return [types.TextContent(type="text", text=_result_to_text(result))]

    return server


async def run_stdio_server():
    try:
        import mcp.server.stdio
        from mcp.server.lowlevel import NotificationOptions
        from mcp.server.models import InitializationOptions
    except ImportError as exc:
        raise RuntimeError("The official MCP SDK is not installed. Run `pip install mcp` or install from requirements.txt.") from exc

    server = create_protocol_server()
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="jarvis",
                server_version="0.0.1",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main():
    asyncio.run(run_stdio_server())


SYSTEM_PROMPT = f"""
You are an AI assistant that converts user commands into tool calls.

Return ONLY valid JSON in this format:

{{
  "tool": "tool_name",
  "arguments": {{...}}
}}

Rules:
- Always choose the best matching tool
- Extract arguments clearly
- If no tool is relevant, return:
  {{ "tool": "none", "arguments": {{}} }}
- Do NOT explain anything
- Do NOT return text outside JSON

Available tools:
{TOOLS}
"""


if __name__ == "__main__":
    main()
