import os
import re
from typing import ClassVar

import requests
from dotenv import load_dotenv

from src.utilz.logger import logger_

load_dotenv()


class BlynkController:
    AUTH_TOKEN: ClassVar = os.getenv("BLYNK_AUTH_TOKEN")
    BASE_URL: ClassVar = "https://blynk.cloud/external/api"
    RELAY_DEVICES: ClassVar = {
        "room_light": {"relay": 1, "aliases": ["room_light", "room light", "bedroom light", "light in room"]},
        "living_room_light": {"relay": 2, "aliases": ["living_room_light", "living room light", "lounge light", "hall light"]},
        "outdoor_light": {"relay": 3, "aliases": ["outdoor_light", "outdoor light", "outside light", "porch light"]},
        "kitchen_light": {"relay": 4, "aliases": ["kitchen_light", "kitchen light", "light in kitchen", "kitchen lamp"]},
    }

    def __init__(self):
        # Relay mapping:
        # V1-V4 -> relay control
        # V5-V8 -> relay status
        # V0 -> uptime
        self.RELAY_PIN_MAP = {
            1: {"control": "V1", "status": "V5"},
            2: {"control": "V2", "status": "V6"},
            3: {"control": "V3", "status": "V7"},
            4: {"control": "V4", "status": "V8"},
        }

    # ========== PUBLIC METHODS ==========

    def devices_info(self) -> str:
        string = ""
        for k, v in self.RELAY_DEVICES.items():
            string += f"{k} ({v.get('aliases', [])})\n"
        return string

    def turn_on(self, relay_number: int):
        return self._digital_write(self._get_control_pin(relay_number), 1)

    def turn_off(self, relay_number: int):
        return self._digital_write(self._get_control_pin(relay_number), 0)

    def get_status(self, relay_number: int) -> bool:
        value = self._get_pin_value(self._get_status_pin(relay_number))
        return str(value) == "1"

    def is_online(self) -> bool:
        url = f"{self.BASE_URL}/isHardwareConnected?token={self.AUTH_TOKEN}"
        try:
            response = self._request(url)
            return str(response) == "True"
        except Exception as e:
            logger_.error(f"Error checking device status: {e}")
            return False

    def get_uptime(self, uptime_pin: str = "V0") -> int:
        try:
            value = self._get_pin_value(uptime_pin)
            return int(value)
        except Exception as e:
            logger_.error(f"Error getting uptime from {uptime_pin}: {e}")
            return -1

    def handle_text_command(self, command: str, assistant=None):
        matches = re.finditer(r"\b(one|two|three|four|\d+|on|off)\b", command.lower())
        matched = [match.group() for match in matches]

        text_to_relay = {
            "1": 1,
            "one": 1,
            "2": 2,
            "two": 2,
            "3": 3,
            "three": 3,
            "4": 4,
            "four": 4,
        }

        state = None
        relay_number = None

        for word in matched:
            if word in ["on", "off"]:
                state = word
            elif word in text_to_relay:
                relay_number = text_to_relay[word]

        if state and relay_number:
            success = self.turn_on(relay_number) if state == "on" else self.turn_off(relay_number)
            if assistant:
                if success:
                    assistant.say(f"Turning {state} relay {relay_number}")
                else:
                    assistant.say(f"Failed to turn {state} relay {relay_number}")
        else:
            if assistant:
                assistant.say("Sorry, I couldn't understand which relay or state you meant.")

    def set_device_state(self, device: str, state: str) -> dict:
        device = device.strip().lower()
        state = state.strip().lower()

        if state not in {"on", "off"}:
            return {"ok": False, "error": f"Invalid state: {state}"}

        device_cfg = self.RELAY_DEVICES.get(device)
        if not device_cfg:
            return {"ok": False, "error": f"Unknown device: {device}"}

        relay_number = device_cfg["relay"]

        success = self.turn_on(relay_number) if state == "on" else self.turn_off(relay_number)

        return {"ok": success, "device": device, "relay": relay_number, "state": state, "message": f"Turned {state} {device}" if success else f"Failed to turn {state} {device}"}

    # ========== PRIVATE HELPERS ==========

    def _url(self, action: str, pin: str, value: int | None = None) -> str:
        url = f"{self.BASE_URL}/{action}?token={self.AUTH_TOKEN}&pin={pin}"
        if value is not None:
            url += f"&value={value}"
        return url

    def _request(self, url: str):
        if not self.AUTH_TOKEN:
            raise RuntimeError("BLYNK_AUTH_TOKEN is not configured")
        response = requests.get(url)
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            return response.text

    def _digital_write(self, pin: str, value: int) -> bool:
        url = self._url("update", pin, value)
        try:
            self._request(url)
            return True
        except Exception as e:
            logger_.error(f"Error updating pin {pin} to {value}: {e}")
            return False

    def _get_pin_value(self, pin: str):
        url = self._url("get", pin)
        data = self._request(url)
        return data[0] if isinstance(data, list) else data

    def _get_control_pin(self, relay_number: int) -> str:
        return self.RELAY_PIN_MAP[relay_number]["control"]

    def _get_status_pin(self, relay_number: int) -> str:
        return self.RELAY_PIN_MAP[relay_number]["status"]


blynk = BlynkController()
