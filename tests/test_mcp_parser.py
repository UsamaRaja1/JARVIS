import unittest

from src.mcp.parser import _parse_json_response


class MCPParserTests(unittest.TestCase):
    def test_parses_open_project_tool_call(self):
        payload = """
```json
[
  {"tool": "open_project", "arguments": {"name": "jarvis"}}
]
```
"""
        parsed = _parse_json_response(payload)
        self.assertEqual(parsed[0]["tool"], "open_project")
        self.assertEqual(parsed[0]["arguments"]["name"], "jarvis")

    def test_parses_search_web_tool_call(self):
        payload = '{"tool":"search_web","arguments":{"query":"fastapi auth","provider":"google"}}'
        parsed = _parse_json_response(payload)
        self.assertEqual(parsed["tool"], "search_web")
        self.assertEqual(parsed["arguments"]["provider"], "google")

    def test_parses_transcribe_audio_tool_call(self):
        payload = '{"tool":"transcribe_audio","arguments":{"query":"my latest recording"}}'
        parsed = _parse_json_response(payload)
        self.assertEqual(parsed["tool"], "transcribe_audio")
        self.assertEqual(parsed["arguments"]["query"], "my latest recording")


if __name__ == "__main__":
    unittest.main()
