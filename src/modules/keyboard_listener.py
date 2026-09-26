import contextlib
import threading
import time

from pynput import keyboard

from src.utilz.logger import logger_


class KeyboardListener:
    def __init__(self):
        self.key_state = {chr(c): False for c in range(ord("a"), ord("z") + 1)}
        self._ctrl_pressed = False
        self._alt_pressed = False
        self._shift_pressed = False
        self._cmd_pressed = False
        self.double_press_window = 0.3
        self._last_modifier_press = {}
        self._wake_event = threading.Event()
        self._wake_key = None
        self._listener_lock = threading.Lock()
        self._ctrl_keys = self._collect_keys("ctrl", "ctrl_l", "ctrl_r")
        self._alt_keys = self._collect_keys("alt", "alt_l", "alt_r")
        self._shift_keys = self._collect_keys("shift", "shift_l", "shift_r")
        self._cmd_keys = self._collect_keys("cmd", "cmd_l", "cmd_r")
        self.listener = self._start_keyboard_listener()

    def _start_keyboard_listener(self):
        listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        listener.daemon = True
        listener.start()
        logger_.info("Keyboard listener started")
        return listener

    def _listener_is_alive(self):
        return bool(self.listener and self.listener.is_alive())

    def ensure_listener(self):
        with self._listener_lock:
            if self._listener_is_alive():
                return False

            if self.listener:
                with contextlib.suppress(Exception):
                    self.listener.stop()

            self._ctrl_pressed = False
            self._alt_pressed = False
            self._shift_pressed = False
            self._cmd_pressed = False
            self._last_modifier_press.clear()
            self.listener = self._start_keyboard_listener()
            logger_.warning("Keyboard listener was not alive and has been restarted")
            return True

    @staticmethod
    def _collect_keys(*key_names):
        return tuple(getattr(keyboard.Key, key_name) for key_name in key_names if hasattr(keyboard.Key, key_name))

    @staticmethod
    def _normalize_modifier_key(key):
        for key_name in ("alt_r", "shift_r"):
            if hasattr(keyboard.Key, key_name) and key == getattr(keyboard.Key, key_name):
                return key_name
        return None

    def _mark_modifier_press(self, key_name):
        now = time.time()
        last_press = self._last_modifier_press.get(key_name)
        if last_press and now - last_press <= self.double_press_window:
            self._wake_key = key_name
            self._wake_event.set()
            self._last_modifier_press[key_name] = 0
            logger_.info("Wake event is set")
            return
        self._last_modifier_press[key_name] = now

    def consume_wake_event(self):
        self.ensure_listener()

        if not self._wake_event.is_set():
            return None

        wake_key = self._wake_key
        self._wake_key = None
        self._wake_event.clear()
        return wake_key

    def stop(self):
        if self.listener:
            self.listener.stop()
            self.listener = None

    def _on_press(self, key):
        try:
            modifier_key = self._normalize_modifier_key(key)
            if modifier_key:
                self._mark_modifier_press(modifier_key)

            if key in self._ctrl_keys:
                self._ctrl_pressed = True
                return

            if key in self._alt_keys:
                self._alt_pressed = True
                return

            if key in self._shift_keys:
                self._shift_pressed = True
                return

            if key in self._cmd_keys:
                self._cmd_pressed = True
                return

            # ---- Shortcuts ----
            if self._ctrl_pressed and self._alt_pressed and key.char in self.key_state:
                self.key_state[key.char] = True

        except AttributeError:
            pass
        except Exception as e:
            logger_.error(f"Keyboard listener on_press failed: {e}")

    def _on_release(self, key):
        try:
            if key in self._ctrl_keys:
                self._ctrl_pressed = False

            if key in self._alt_keys:
                self._alt_pressed = False

            if key in self._shift_keys:
                self._shift_pressed = False

            if key in self._cmd_keys:
                self._cmd_pressed = False

            if key.char in self.key_state:
                self.key_state[key.char] = False
        except AttributeError:
            pass
        except Exception as e:
            logger_.error(f"Keyboard listener on_release failed: {e}")
        if key == keyboard.Key.esc:
            return False
