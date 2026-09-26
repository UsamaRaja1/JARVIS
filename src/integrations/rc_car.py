import re
import threading
import time

import cv2
import numpy as np
from pynput import keyboard

from src.integrations.arduino_controller import ArduinoController
from src.utilz.logger import logger_


class RCCarController:
    IPV4_PATTERN = re.compile(
        r"^((25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}"
        r"(25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)$"
    )

    def __init__(self, arduino: ArduinoController = None):
        self.key_state = {chr(c): False for c in range(ord("a"), ord("z") + 1)}
        self.arduino = arduino if arduino else ArduinoController()
        self.cap = None
        self.front_light = 0
        self.toggle_time = time.time()
        self.listener = self._start_keyboard_listener()
        self.is_running = True
        self.latest_response = {}
        self.response_lock = threading.Lock()
        self.response_event = threading.Event()
        self.running = True

        # Piggybacked text command sent on the next control frames
        # (e.g. "ip", "status"). Cleared by whoever set it once a reply arrives.
        self._request_text = ""
        self._cam_y = 127

        # Clear any stale bytes that may have been buffered between runs.
        if self.arduino.arduino_serial:
            try:
                self.arduino.arduino_serial.reset_input_buffer()
            except Exception as e:
                logger_.warning("reset_input_buffer failed: %s", e)

        self.serial_thread = threading.Thread(target=self._serial_reader, daemon=True)
        self.control_thread = threading.Thread(target=self._control_loop, daemon=True)

        self.serial_thread.start()
        self.control_thread.start()

    # -------------------------
    # SERIAL READER THREAD
    # -------------------------
    def _serial_reader(self):
        """Parse 'T,<ping>,<pwm>,<message>\\n' telemetry frames from the sketch."""
        while self.running:
            try:
                ser = self.arduino.arduino_serial
                if not ser:
                    time.sleep(0.05)
                    continue

                line = ser.readline()  # blocks up to the serial read timeout
                if not line:
                    continue

                s = line.decode("ascii", errors="ignore").strip()
                if not s.startswith("T,"):
                    continue

                parts = s.split(",", 3)
                if len(parts) < 4:
                    continue

                try:
                    parsed = {
                        "ping": int(parts[1]),
                        "pwm": int(parts[2]),
                        "message": parts[3],
                    }
                except ValueError:
                    continue

                with self.response_lock:
                    self.latest_response = parsed
                self.response_event.set()

            except Exception as e:
                logger_.error("Serial read error: %s", e)
                time.sleep(0.05)

    # -------------------------
    # CONTROL LOOP (50 Hz)
    # -------------------------
    def _control_loop(self):
        last_send = 0

        while self.running:
            if time.time() - last_send >= 0.02:  # 50 Hz
                last_send = time.time()

                control_data = self._get_control_values()

                try:
                    self.arduino.send_payload(**control_data)
                except Exception as e:
                    logger_.error("Send error:", e)

            time.sleep(0.001)

    def _start_keyboard_listener(self):
        listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        listener.daemon = True
        listener.start()
        return listener

    def _on_press(self, key):
        try:
            if key.char in self.key_state:
                self.key_state[key.char] = True
        except AttributeError:
            pass

    def _on_release(self, key):
        try:
            if key.char in self.key_state:
                self.key_state[key.char] = False
        except AttributeError:
            pass
        if key == keyboard.Key.esc:
            return False

    def _is_valid_ipv4(self, ip):
        return self.IPV4_PATTERN.match(ip) is not None

    def _get_stream_ip(self, timeout: int = 20):
        """Ask the car for its camera IP by piggybacking text='ip' on the
        control stream and waiting for the background reader to deliver a
        valid IPv4 message. Avoids racing the reader thread on the serial port.
        """
        logger_.info("Getting IP address...")
        self._request_text = "ip"
        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                self.response_event.wait(timeout=0.2)
                self.response_event.clear()
                with self.response_lock:
                    msg = self.latest_response.get("message", "") if isinstance(self.latest_response, dict) else ""
                if msg and self._is_valid_ipv4(msg):
                    return msg
            logger_.info("Timeout occur for getting IP")
            return None
        finally:
            self._request_text = ""

    def connect_camera(self, timeout: int = 20):
        ip = self._get_stream_ip(timeout=timeout)
        if ip:
            logger_.info(f"Connecting to camera at: http://{ip}")
            stream_url = f"http://{ip}:81/stream"
            self.cap = cv2.VideoCapture(stream_url)
            if not self.cap.isOpened():
                logger_.info("Error: Cannot open video stream")
                return None
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return self.cap
        else:
            logger_.info("No camera connected")
        return None

    def _get_control_values(self):
        speed = 220 if self.key_state["w"] else 30 if self.key_state["s"] else 127
        turn = 50 if self.key_state["a"] else 200 if self.key_state["d"] else 127
        y = -10 if self.key_state["i"] else 10 if self.key_state["k"] else 0
        x = 50 if self.key_state["j"] else 210 if self.key_state["l"] else 127
        aux2 = int(self.key_state["h"])
        y = self._cam_y + y
        if y < 0:
            y = 0
        elif y > 255:
            y = 255
        self._cam_y = y

        if self.key_state["f"] and (time.time() - self.toggle_time > 0.3):
            if self.front_light == 0:
                self.front_light = 127
            elif self.front_light == 127:
                self.front_light = 255
            else:
                self.front_light = 0
            self.toggle_time = time.time()

        return dict(
            Y1=speed,
            X2=turn,
            X1=x,
            Y2=y,
            AUX4=1,
            AUX5=1,
            AUX2=aux2,
            AUX3=int(self.front_light),
            text=self._request_text,
        )

    def run(self):
        self.connect_camera()
        if not self.cap:
            logger_.info("No camera connected, continuing without it.")

        cv2.namedWindow("IP Camera Stream", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("IP Camera Stream", 680, 520)
        time.time()

        try:
            frame = np.zeros((480, 640, 3), np.uint8)

            while self.running:
                if self.cap:
                    ret, new_frame = self.cap.read()
                    if not ret:
                        logger_.info("Failed to retrieve frame")
                        break

                else:
                    new_frame = frame.copy()

                # Get latest telemetry (non-blocking)
                with self.response_lock:
                    data = self.latest_response.copy() if isinstance(self.latest_response, dict) else self.latest_response

                cv2.putText(new_frame, f"Ping: {data.get('ping', -1)} | {data.get('message', '')}", (10, 30), cv2.FONT_HERSHEY_COMPLEX, 0.5, (0, 255, 0), 1)

                cv2.imshow("IP Camera Stream", new_frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                time.sleep(0.01)

            self.stop()

        finally:
            if self.cap:
                self.cap.release()
            cv2.destroyAllWindows()

    def stop(self):
        self.is_running = False
        self.running = False
        self.response_event.set()  # unblock any waiters
        self.listener.stop()
        if self.cap:
            self.cap.release()


if __name__ == "__main__":
    arduino = ArduinoController(baud_rate=115200)
    time.sleep(1)
    if not arduino.arduino_serial:
        exit()
    controller = RCCarController(arduino=arduino)
    controller.run()
