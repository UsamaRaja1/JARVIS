import datetime
import os
import re

import pyautogui

from src.configs import BOT_NAME, USER_NAME
from src.llm.chat_ai import chat_ai
from src.mcp.parser import parse_intent
from src.mcp.server import MCPServer
from src.modules.semantic_search import ss_obj
from src.modules.shared_data import get_name
from src.utilz.logger import logger_
from src.utilz.modules import extract_number, get_greetings, get_weather, set_brightness, setup_workspace
from src.utilz.pycharm_launcher import show_all_projects
from src.utilz.switch_app import switch_desktop

mcp_server = MCPServer()
CONVERSATION_MODE = False
DESKTOP_MCP_TOOL_NAMES = {"open_website", "search_web", "open_app", "focus_app", "open_project", "open_directory", "list_active_apps", "refresh_desktop_indexes"}


async def lights_control(command, arduino, assistant):
    # Match valid words or digits in the command
    matches = re.finditer(r"\b(one|on|off|\d+|red|green|blue|white|orange)\b", command)
    matched_strings = [match.group() for match in matches]
    data_str = matched_strings.copy()
    # LED index and state mapping
    color_to_index = {"red": 0, "1": 0, "one": 0, "green": 1, "2": 1, "blue": 2, "3": 2, "white": 3, "4": 3, "orange": 4, "5": 4}

    state_to_value = {"on": 255, "off": 0}

    led = arduino.leds

    for string in matched_strings:
        string = string.lower()  # Ensure case-insensitivity
        if string in color_to_index:
            led_index = color_to_index[string]
            if matched_strings[0] in state_to_value:  # Check the state ('on' or 'off')
                led[led_index] = state_to_value[matched_strings[0]]

    data = ", ".join([str(l) for l in led])
    data = f"{{lights: [{data}]}} \n"

    if arduino.send_data(data):
        response = f"turning {' '.join(data_str)} light"
        assistant.say(response)

    else:
        response = f"Serial connection not established. Cannot turn {data_str} lights."
        assistant.say(response)


def _format_mcp_response(result):
    if result is None:
        return None
    if isinstance(result, str):
        return result
    if isinstance(result, dict) and result.get("message"):
        return result["message"]
    return str(result)


def should_try_desktop_mcp(command: str) -> bool:
    lowered = command.lower().strip()
    return any(
        phrase in lowered
        for phrase in (
            "open ",
            "launch ",
            "start ",
            "focus ",
            "switch to ",
            "show active ",
            "list active ",
            "running app",
            "running window",
            "search ",
            "look up ",
            "find ",
            "play ",
            "refresh index",
            "refresh desktop",
            "rebuild index",
        )
    )


async def try_mcp_fallback(command: str, assistant, speech_rate: int = 190, tool_names: set[str] | None = None, hint: str | None = None) -> bool:
    tools = mcp_server.list_tools()
    if tool_names is not None:
        tools = [tool for tool in tools if tool["name"] in tool_names]
    if not tools:
        return False

    try:
        intents = await parse_intent(command, tools, hint=hint)
        if not isinstance(intents, dict | list):
            logger_.info(f"MCP parser returned {type(intents)} intents: {intents}")
            return False

        if isinstance(intents, dict):
            intents = [intents]

        status = True
        for intent in intents:
            tool_name = intent.get("tool")
            arguments = intent.get("arguments") or {}
            if not tool_name or tool_name == "none":
                status = False
                continue
            if tool_names is not None and tool_name not in tool_names:
                logger_.warning(f"MCP parser returned disallowed tool {tool_name} for command {command!r}")
                status = False
                continue

            result = await mcp_server.call_tool_async(tool_name, arguments)
            response = _format_mcp_response(result)
            if response:
                assistant.say(response, rate=speech_rate)
        return status
    except Exception as exc:
        logger_.error(f"MCP fallback failed for command {command!r}: {exc}")
        return False


async def perform_action(command, arduino, face_recognizer, assistant, user_name: str):
    global CONVERSATION_MODE
    speech_rate = 190  # Adjust this value for different speech rates (words per minute).

    if "what" in command and "time" in command:
        now = datetime.datetime.now()
        current_time = now.strftime("%I:%M %p")  # %I for 12-hour format, %p for AM/PM
        response = f"The current time is {current_time}."
        assistant.say(response, rate=speech_rate)

    elif "date" in command and ("today" in command or "current" in command):
        current_date = datetime.date.today()
        formatted_date = current_date.strftime("%d %B %Y")  # 01 Jan 2025
        response = f"Today is {formatted_date}."
        assistant.say(response, rate=speech_rate)

    elif "weather" in command:
        city = command.split("weather in ")[-1]
        response = get_weather(city)
        assistant.say(response, rate=speech_rate)

    elif "show desktop" in command:
        pyautogui.hotkey("winleft", "d")

    elif ("minimize" in command or "minimise" in command) and "app" in command:
        pyautogui.hotkey("winleft", "m")

    elif ("unlock" in command and "pc" in command) or "enter password" in command or "login" in command:
        unlock_enabled = os.getenv("ENABLE_PC_UNLOCK", "false").strip().lower() in {"1", "true", "yes", "on"}
        password = os.getenv("AUTH_PASSWORD")
        if not unlock_enabled or not password:
            assistant.say("Computer unlock is disabled in the local configuration.", rate=speech_rate)
        elif assistant.is_user_authorized():
            response = f"Unlocking PC {USER_NAME}"
            assistant.say(response, rate=speech_rate)
            pyautogui.write(password)
            pyautogui.press("enter")
        else:
            response = "I'm sorry, but you are not authorized."
            assistant.say(response, rate=speech_rate)

    elif ("lock" in command and "pc" in command) or "logout" in command:
        if assistant.is_user_authorized():
            pyautogui.hotkey("winleft", "l")
            response = f"Locking PC {USER_NAME}"
            assistant.say(response, rate=speech_rate)
        else:
            response = "I'm sorry, but you are not authorized."
            assistant.say(response, rate=speech_rate)

    # elif "turn " in command and any(query in command for query in ["light", "led", "bulb", "relay"]):
    #     blynk.handle_text_command(command, assistant)
    # await lights_control(command, arduino, assistant)

    elif "switch to" in command and "tab" in command:
        tab_num = extract_number(command)
        response = f"switching to tab {tab_num}"
        pyautogui.hotkey("ctrl", str(tab_num))
        assistant.say(response, rate=speech_rate)

    elif "switch to" in command and "desktop" in command:
        desktop_num = extract_number(command)
        response = f"Switching to desktop {desktop_num}"
        assistant.say(response, rate=speech_rate)
        response = switch_desktop(desktop_num)
        if response:
            assistant.say(response, rate=speech_rate)

    elif "deactivate" in command and "conversation mode" in command:
        CONVERSATION_MODE = False
        response = "Conversation mode is now deactivated."
        assistant.say(response, rate=speech_rate)

    elif "activate" in command and "conversation mode" in command:
        CONVERSATION_MODE = True
        response = "Conversation mode is now activated."
        assistant.say(response, rate=speech_rate)

    elif "switch" in command and "window" in command:
        pyautogui.hotkey("alt", "tab")
        response = "switching window"
        assistant.say(response, rate=speech_rate)

    elif ("show" in command or "list" in command) and "project" in command:
        show_all_projects()

    elif "how many" in command and ("person") in command:
        names = get_name()
        response = f"There are {len(names)} persons in the frame."
        assistant.say(response)

    elif "set" in command and "brightness" in command:
        set_brightness(command)

    elif "set" in command and "my" in command and "workspace" in command:
        setup_workspace(user_name.lower())

    elif "set" in command and "night mode" in command:
        set_brightness(brightness=2)

    elif "set" in command and "day mode" in command:
        set_brightness(brightness=8)

    elif "connect" in command and "arduino" in command:
        arduino.establish_connection()

    # elif 'connect' in command and 'car' in command:
    #     arduino.send_data()

    elif should_try_desktop_mcp(command):
        if await try_mcp_fallback(command, assistant, speech_rate=speech_rate, tool_names=DESKTOP_MCP_TOOL_NAMES, hint="desktop"):
            return

    else:
        result = ss_obj.process_text(query=command, from_file=True, top_k=1)
        response = result["content"][0].split("|")[-1]
        if CONVERSATION_MODE:
            if "[DESCRIBE_IMAGE]" in response:
                image = face_recognizer.get_current_image()
                response = await chat_ai.chat(query=command, image=image)
                response = response.get("content") if response.get("content") else f"I'm sorry, but I cannot process that at the moment. {error if (error := response.get('error')) else ''}"
            else:
                response = await chat_ai.chat(command)
                response = response.get("content")

            if response:
                assistant.say(response, rate=speech_rate)
        else:
            # if await try_mcp_fallback(command, assistant, speech_rate=speech_rate):
            #     return
            if result["scores"][0] > 200:
                name = get_name()
                response = (
                    response.replace("[NAME]", user_name).replace("[NAMES]", ", ".join(name)).replace("[USER_NAME]", USER_NAME).replace("[BOT_NAME]", BOT_NAME).replace("[GREETING]", get_greetings())
                )

                if "[NUMBER]" in response:
                    name = get_name()
                    response = f"There is {len(name)} person in the frame" if len(name) <= 1 else f"There are {len(name)} persons in the frame"

                if "[GREETING]" in response:
                    response = response.replace("[GREETING]", get_greetings())

                if "[DESCRIBE_IMAGE]" in response:
                    response = "Please activate the conversation mode, and turn on camera"

                assistant.say(response)
            else:
                logger_.info(f"Ignored: {result}")
                if await try_mcp_fallback(command, assistant, speech_rate=speech_rate):
                    return
