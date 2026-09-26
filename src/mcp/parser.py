import json
import re
from typing import Any

from src.llm.chat_ai import chat_ai
from src.utilz.logger import logger_

DESKTOP_INTENT_PROMPT = """
You convert desktop-assistant voice commands into MCP tool calls.

Return ONLY valid JSON as either:
[
  {
    "tool": "tool_name",
    "arguments": {}
  }
]
or:
{
  "tool": "tool_name",
  "arguments": {}
}

Rules:
- Choose the single best tool unless the command explicitly requires multiple steps.
- Use `search_web` for web searches. If no provider is named, default to `google`.
- Use `open_app` for opening an installed application like chrome, slack, pycharm, or terminal.
- Use `focus_app` for focusing an already-running application or window.
- Use `open_project` for project/repo/workspace opening requests.
- Use `open_directory` for folder/directory/path opening requests.
- Use `list_active_apps` for listing running or active desktop applications/windows.
- Use `refresh_desktop_indexes` for rebuild/refresh/reindex requests.
- Use `transcribe_audio` for transcription/speech-to-text requests on audio or video files. Pass the
  user's own wording as `query` verbatim -- do not invent a specific filename, extension, or folder
  they did not mention (audio/video files can have any extension).
- For direct websites like `open github.com`, use `open_website`.
- If no tool fits, return:
  [{"tool":"none","arguments":{}}]
- No prose. No markdown fences.
"""

GENERAL_INTENT_PROMPT = """
You convert user commands into MCP tool calls.

Return ONLY valid JSON as either:
[
  {
    "tool": "tool_name",
    "arguments": {}
  }
]
or:
{
  "tool": "tool_name",
  "arguments": {}
}

Rules:
- Choose the best matching tool.
- Extract arguments clearly.
- If no tool fits, return:
  [{"tool":"none","arguments":{}}]
- No prose. No markdown fences.
"""


def _extract_json_block(text: str) -> str:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    for pattern in (r"\[\s*\{.*\}\s*\]", r"\{.*\}"):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(0)
    return text


def _parse_json_response(text: str) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(text, dict | list):
        return text
    payload = _extract_json_block(text)
    parsed = json.loads(payload)
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        return parsed
    raise ValueError(f"Unexpected MCP parser payload type: {type(parsed)}")


async def parse_intent(command: str, tools: list, hint: str | None = None):
    prompt = DESKTOP_INTENT_PROMPT if hint == "desktop" else GENERAL_INTENT_PROMPT
    system_prompt = f"{prompt}\nAvailable tools:\n{tools}"
    response = await chat_ai.chat(messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": command}])
    content = response.get("content", "")
    try:
        return _parse_json_response(content)
    except Exception as exc:
        logger_.error(f"Failed to parse MCP intent response for {command!r}: {exc}; raw={content!r}")
        return [{"tool": "none", "arguments": {}}]
