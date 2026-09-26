import asyncio
import webbrowser

from src.integrations.blynk import blynk
from src.mcp.tools import register_tool
from src.utilz.desktop_resolver import desktop_resolver


@register_tool(name="get_weather", description="Get weather for a city", schema={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]})
def weather_tool(city: str):
    from src.utilz.modules import get_weather

    return get_weather(city)


@register_tool(name="open_website", description="Open a website like youtube, google, etc.", schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})
def open_website_tool(query: str):
    from src.utilz.web_search import resolve_website_url

    url, web = resolve_website_url(query)
    if url:
        webbrowser.open(url)
        return f"Opening {web}"
    else:
        webbrowser.open(query)
        return f"Opening {query}"


@register_tool(
    name="search_web",
    description="Search a provider like Google, YouTube, GitHub, Wikipedia, or Maps and open the results page.",
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
            "provider": {"type": "string", "enum": ["google", "youtube", "github", "wikipedia", "maps"], "description": "The target search provider."},
        },
        "required": ["query", "provider"],
    },
)
def search_web_tool(query: str, provider: str):
    result = desktop_resolver.search_web(query=query, provider=provider)
    return result.message


@register_tool(
    name="open_app",
    description="Open an application by name. If the app is already running, focus it instead of launching a new instance when possible.",
    schema={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Application name such as chrome, pycharm, slack, or terminal."}},
        "required": ["name"],
    },
)
def open_app_tool(name: str):
    result = desktop_resolver.open_app(name)
    return result.message


@register_tool(
    name="focus_app",
    description="Focus an already-running application by name.",
    schema={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Running application name to focus."}},
        "required": ["name"],
    },
)
def focus_app_tool(name: str):
    result = desktop_resolver.focus_app(name)
    return result.message


@register_tool(
    name="open_project",
    description="Open a local project by name using indexed project folders. Shows the chooser UI when multiple close matches exist.",
    schema={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Project name to open."}},
        "required": ["name"],
    },
)
def open_project_tool(name: str):
    result = desktop_resolver.open_project(name)
    return result.message


@register_tool(
    name="open_directory",
    description="Open a local directory by name using indexed folders. Shows the chooser UI when multiple close matches exist.",
    schema={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Directory or folder name to open."}},
        "required": ["name"],
    },
)
def open_directory_tool(name: str):
    result = desktop_resolver.open_directory(name)
    return result.message


@register_tool(
    name="list_active_apps",
    description="List currently active desktop application windows.",
    schema={"type": "object", "properties": {}},
)
def list_active_apps_tool():
    return desktop_resolver.list_active_apps()


@register_tool(
    name="refresh_desktop_indexes",
    description="Refresh cached application, project, and directory indexes used by desktop opening tools.",
    schema={
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["apps", "projects", "directories", "all"],
                "description": "Which desktop indexes to refresh.",
            }
        },
    },
)
def refresh_desktop_indexes_tool(scope: str = "all"):
    result = desktop_resolver.refresh_indexes(scope=scope, force=True)
    return result.message


@register_tool(
    name="set_device_state",
    description=("Turn a known home device on or off. Use this for devices like room light, living room light, outdoor light, kitchen light. Examples: room_light on, fan off."),
    schema={
        "type": "object",
        "properties": {
            "device": {"type": "string", "enum": list(blynk.RELAY_DEVICES.keys()), "description": f"Logical device name such as {blynk.devices_info()}"},
            "state": {"type": "string", "enum": ["on", "off"], "description": "Desired state"},
        },
        "required": ["device", "state"],
    },
)
def set_device_state_tool(device: str, state: str):
    result = blynk.set_device_state(device=device, state=state)
    return result["message"] if result["ok"] else f"Error: {result['error']}"


@register_tool(
    name="playback_control",
    description="Control media playback (play, pause).",
    schema={
        "type": "object",
        "properties": {"action": {"type": "string", "enum": ["play", "pause"], "description": "Playback action."}},
        "required": ["action"],
    },
)
def playback_control(action: str):
    from src.utilz.os_controls import handle_playback_command

    return handle_playback_command(action)


@register_tool(
    name="media_control",
    description="Navigate media tracks.",
    schema={
        "type": "object",
        "properties": {"action": {"type": "string", "enum": ["next", "previous"], "description": "Track navigation action."}},
        "required": ["action"],
    },
)
def media_control(action: str):
    from src.utilz.os_controls import handle_media_command

    return handle_media_command(action)


@register_tool(
    name="transcribe_audio",
    description=(
        "Transcribe an audio or video file into text using the local Whisper model. Resolves the file "
        "from a natural-language description (e.g. 'the interview I recorded yesterday', 'the recording "
        "I just downloaded') when an exact path isn't given -- audio/video files can have any extension, "
        "so pass the user's own wording rather than guessing a specific filename or format. Saves a "
        "transcript text file alongside the source."
    ),
    schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Natural-language description of the audio/video file to transcribe, or a direct file path. "
                    "Use the user's own wording verbatim -- do not invent a specific extension, filename, or "
                    "folder they did not mention."
                ),
            },
            "open_folder": {"type": "boolean", "description": "Open the containing folder after transcription completes.", "default": False},
        },
        "required": ["query"],
    },
)
async def transcribe_audio_tool(query: str, open_folder: bool = False):
    from src.utilz.transcription_service import transcription_service

    result = await asyncio.to_thread(transcription_service.transcribe, query, open_folder)
    return result.message


@register_tool(
    name="volume_control",
    description="Adjust the system volume.",
    schema={
        "type": "object",
        "properties": {"action": {"type": "string", "enum": ["volume_up", "volume_down", "mute"], "description": "Volume adjustment."}},
        "required": ["action"],
    },
)
def volume_control(action: str):
    from src.utilz.os_controls import handle_volume_command

    return handle_volume_command(action)
