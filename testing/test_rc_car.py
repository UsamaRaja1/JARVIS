import sys
import threading
import time
import types
import unittest
from queue import Queue


class FakeListener:
    def __init__(self, **_kwargs):
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


fake_keyboard = types.SimpleNamespace(Listener=FakeListener, Key=types.SimpleNamespace(esc="esc"))
sys.modules.setdefault("pynput", types.SimpleNamespace(keyboard=fake_keyboard))
sys.modules.setdefault("src.integrations.arduino_controller", types.SimpleNamespace(ArduinoController=object))
sys.modules.setdefault(
    "src.utilz.logger",
    types.SimpleNamespace(logger_=types.SimpleNamespace(error=lambda *_args: None, info=lambda *_args: None, warning=lambda *_args: None)),
)

from src.integrations.rc_car import RCCarController


class FakeArduino:
    arduino_serial = None

    def __init__(self):
        self.payloads = []

    def send_payload(self, **payload):
        self.payloads.append(payload)


class RCCarControllerTest(unittest.TestCase):
    def test_constructor_is_passive(self):
        controller = RCCarController(FakeArduino())

        self.assertIsNone(controller.listener)
        self.assertIsNone(controller.serial_thread)
        self.assertIsNone(controller.control_thread)
        self.assertFalse(controller.is_running)

    def test_tracking_and_driving_share_one_payload(self):
        arduino = FakeArduino()
        targets = Queue()
        targets.put((42, 84))
        controller = RCCarController(arduino)
        controller.key_state["w"] = True

        controller.start_controls(targets, keyboard_control=False)
        time.sleep(0.05)
        controller.stop()

        active_payloads = [payload for payload in arduino.payloads if payload.get("Y1") == 220]
        self.assertTrue(active_payloads)
        self.assertEqual(active_payloads[-1]["X1"], 42)
        self.assertEqual(active_payloads[-1]["Y2"], 84)
        self.assertEqual(arduino.payloads[-1], {})

    def test_external_stop_event_stops_controls_and_sends_neutral_payload(self):
        arduino = FakeArduino()
        stop_event = threading.Event()
        controller = RCCarController(arduino)

        controller.start_controls(keyboard_control=False, stop_event=stop_event)
        stop_event.set()
        controller.control_thread.join(timeout=1)

        self.assertFalse(controller.is_running)
        self.assertFalse(controller._controls_running.is_set())
        self.assertEqual(arduino.payloads[-1], {})
        controller.stop()


if __name__ == "__main__":
    unittest.main()
