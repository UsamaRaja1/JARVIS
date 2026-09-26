import glob
import time
from typing import ClassVar

import serial

from src.utilz.logger import logger_

min_x = 0
max_x = 180
min_y = 60
max_y = 130
prev_x = 90
prev_y = 90

ArduinoSerial = None


# try:
#     # Find the Arduino port
#     ports = glob.glob('/dev/ttyACM*')
#     if not ports:
#         port = '/dev/ttyACM1'
#     else:
#         port = ports[0]
#     ArduinoSerial = serial.Serial(port, 57600, write_timeout=1, timeout=1)
#     logger.info("Serial connection established successfully.")
# except serial.SerialException:
#     logger.info("Error: Serial port not available. Make sure the Arduino is connected.")


class ArduinoController:
    def __init__(self, port=None, baud_rate=57600, write_timeout=1, read_timeout=1):
        self.arduino_serial = None
        self.min_x = 0
        self.max_x = 180
        self.min_y = 60
        self.max_y = 160
        self.prev_x = 90
        self.prev_y = 90
        self.leds = [0, 0, 0, 0, 0]
        self.prev_time = 0
        self.establish_connection(port, baud_rate, write_timeout, read_timeout)

    def establish_connection(self, port=None, baud_rate=57600, write_timeout=1, read_timeout=1, sleep_time=0.5):
        if time.time() - self.prev_time > 10:
            self.prev_time = time.time()
            try:
                if port is None:
                    # Find the Arduino port
                    ports = glob.glob("/dev/ttyACM*")
                    if ports:
                        port = ports[0]
                    else:
                        ports = glob.glob("/dev/ttyUSB*")
                        if ports:
                            port = ports[0]
                        else:
                            logger_.warning("No Arduino serial port found")
                if port:
                    self.arduino_serial = serial.Serial(port, baud_rate, write_timeout=write_timeout, timeout=read_timeout)
                    logger_.info(f"Serial connection established successfully. Port: {port}, Baud rate: {baud_rate}.")
                    time.sleep(sleep_time)
            except serial.SerialException as e:
                logger_.error(f"Error: {e}")
                self.arduino_serial = None

    def send_data(self, data, print_logs=False, receive=False, raise_error=False, string="\n"):
        try:
            if self.arduino_serial:
                if not data.endswith(string):
                    data += string
                data = data.encode("utf-8")
                if print_logs:
                    logger_.info(f"Sending data to Arduino: {data}")
                # self.reset_buffers()
                self.arduino_serial.write(data)
                if receive:
                    data_received = self.receive_data()
                    logger_.info(f"Received data from Arduino: {data_received}") if print_logs else None
                    return data_received
            else:
                self.establish_connection()
            return
        except serial.SerialTimeoutException as e:
            if raise_error:
                raise e
            logger_.error(f"Serial write timeout: {e}")
            # self.reset_buffers()
            return f"Serial write timeout: {e}"
        except Exception as e:
            if raise_error:
                raise e
            logger_.error(f"Serial communication error: {e}")
            self.establish_connection()
            return f"Serial communication error: {e}"

    def receive_data(self, match=b"\n", process_raw=False):
        if self.arduino_serial and self.arduino_serial.in_waiting > 0:
            if process_raw:
                r = self.arduino_serial.read_until(match)
                r = r.decode().strip().split(match)
                if len(r) > 2:
                    data = r[-2]
                    return data
            else:
                data = self.arduino_serial.read_until(match).decode().strip()
                return data
        return None

    def servo_move(self, x_axis, y_axis, p=1, print_logs=False):
        _px, _py = x_axis, y_axis
        if p != 1:
            x_axis = int(self.prev_x * (1 - p) + x_axis * p)
            y_axis = int(self.prev_y * (1 - p) + y_axis * p)

        # logger.info(f"px {px}, py {py} |  x {x_axis}, y {y_axis}  |  prev-x {self.prev_x}, prev-y {self.prev_y}")

        x_axis = min(self.max_x, max(self.min_x, x_axis))
        y_axis = min(self.max_y, max(self.min_y, y_axis))
        data = str({"x_axis": x_axis, "y_axis": y_axis}) + "\n"

        if x_axis != self.prev_x or y_axis != self.prev_y:
            self.send_data(data, print_logs)
            time.sleep(0.003)
            self.prev_x = x_axis
            self.prev_y = y_axis

    # Fixed-field CSV protocol for the NRF24 transmitter sketch
    # (arduino-sketches/NRF24_python_arduino_rc_control.ino).
    # Order must match the Arduino parser exactly.
    _CTRL_FIELDS: ClassVar[tuple[str, ...]] = (
        "X1",
        "Y1",
        "X2",
        "Y2",
        "AUX1",
        "AUX2",
        "AUX3",
        "AUX4",
        "AUX5",
        "AUX6",
        "text",
    )

    _CTRL_DEFAULTS: ClassVar[dict[str, int | str]] = {
        "X1": 127,
        "Y1": 127,
        "X2": 127,
        "Y2": 127,
        "AUX1": 0,
        "AUX2": 0,
        "AUX3": 0,
        "AUX4": 0,
        "AUX5": 0,
        "AUX6": 0,
        "text": "",
    }

    def send_payload(self, print_logs=False, **kwargs):
        vals = {**self._CTRL_DEFAULTS, **kwargs}
        # Strip any embedded newlines from text so we don't break the frame terminator.
        text = str(vals["text"]).replace("\n", "").replace("\r", "").replace(",", "")
        vals["text"] = text
        line = ",".join(str(vals[k]) for k in self._CTRL_FIELDS) + "\n"
        return self.send_data(line, print_logs=print_logs)

    def reset_buffers(self):
        if self.arduino_serial:
            self.arduino_serial.reset_input_buffer()
            self.arduino_serial.reset_output_buffer()
            # self.ArduinoSerial.flush()

    def get_buffer_info(self):
        if self.arduino_serial:
            return self.arduino_serial.in_waiting

    def lights_control(self, lights_data: dict):
        # Map light names to their corresponding LED index in the self.leds array
        light_map = {"red": 0, "green": 1, "blue": 2, "white": 3, "orange": 4}

        data_changed = False

        for light, value in lights_data.items():
            if light in light_map:
                led_index = light_map[light]
                if self.leds[led_index] != value:
                    self.leds[led_index] = value
                    data_changed = True
                    # logger.info(f"{light} set to {self.leds[led_index]}")
            else:
                logger_.info(f"Warning: {light} is not a recognized light color")

        # Only send data if there has been a change
        if data_changed:
            data = ", ".join([str(l) for l in self.leds])
            data = f"{{lights: [{data}]}}\n"
            # Send the data and return the result
            return self.send_data(data, print_logs=True)
        else:
            return None  # No change, nothing to send


def send_data(data, print_logs=False):
    try:
        if ArduinoSerial:
            data = data.encode()
            if print_logs:
                logger_.info(f"Sending data to Arduino: {data}")
                ArduinoSerial.write(data)
                logger_.info(f"Received data: {receive_data()}")
            else:
                ArduinoSerial.write(data)

            return True
    except serial.SerialTimeoutException as e:
        logger_.error(f"Serial write timeout: {e}")
    except Exception as e:
        logger_.error(f"Serial communication error: {e}")
    return False


def receive_data():
    if ArduinoSerial:
        data = ArduinoSerial.read_until(b"\n")
        return data
    else:
        return "No data received, Serial not available."


def reset_buffers():
    if ArduinoSerial:
        ArduinoSerial.reset_input_buffer()
        ArduinoSerial.reset_output_buffer()
        # ArduinoSerial.flush()


def get_buffer_info():
    if ArduinoSerial:
        return ArduinoSerial.in_waiting


def servo_move(x_axis, y_axis, print_logs=False):
    global prev_x, prev_y
    x_axis = min(max_x, max(min_x, x_axis))
    y_axis = min(max_y, max(min_y, y_axis))

    data = str({"x_axis": int(x_axis), "y_axis": int(y_axis)}) + "\n"
    if print_logs:
        logger_.info(data)

    if x_axis != prev_x or y_axis != prev_y:
        # logger.info(receive_data())
        send_data(data, print_logs)
        time.sleep(0.01)
        prev_x = x_axis
        prev_y = y_axis
        # buffer_size = get_buffer_info()
        # logger.info(f"buffer_size: {buffer_size}")
        # if isinstance(buffer_size, int):
        #     if buffer_size > 500:
        # reset_buffers()


def rgb(r, g, b):
    clr = f"{r},{g},{b}\n"
    # if ArduinoSerial:
    ArduinoSerial.write(clr.encode())


r1, g1, b1 = 0, 0, 0


def fade_in(r, g, b):
    global r1, g1, b1
    steps = 5
    delay = 70 / 1000
    # r1, g1, b1 = 0, 0, 0
    for _i in range(0, 256, steps):
        if r1 != r:
            r1 += steps
        if g1 != g:
            g1 += steps
        if b1 != b:
            b1 += steps
        time.sleep(delay)
        rgb(r1, g1, b1)


def fade_out(r, g, b):
    global r1, g1, b1
    steps = 5
    delay = 70 / 1000

    # r1, g1, b1 = 255, 255, 255
    for _i in range(0, 256, steps):
        if r1 != r:
            r1 -= steps
        if g1 != g:
            g1 -= steps
        if b1 != b:
            b1 -= steps

        time.sleep(delay)
        rgb(r1, g1, b1)


def lights():
    l = 1
    t = 5

    for _ in range(200):
        for _i in range(3):
            d = f"on,{l}\n"
            ArduinoSerial.write(d.encode())
            time.sleep(t)
            d = f"of,{l}\n"
            ArduinoSerial.write(d.encode())
            time.sleep(0.001)
            l += 1
            if l == 4:
                l = 1

        d = "on,1,2\n"
        ArduinoSerial.write(d.encode())
        time.sleep(t)
        d = "of,1,2\n"
        ArduinoSerial.write(d.encode())

        d = "on,2,3\n"
        ArduinoSerial.write(d.encode())
        time.sleep(t)
        d = "of,2,3\n"
        ArduinoSerial.write(d.encode())

        # d = f'on,1,3\n'
        # ArduinoSerial.write(d.encode())
        # time.sleep(t)
        # d = f'of,1,3\n'
        # ArduinoSerial.write(d.encode())

        d = "on,1,2,3\n"
        ArduinoSerial.write(d.encode())
        time.sleep(t)
        d = "of,1,2,3\n"
        ArduinoSerial.write(d.encode())


def main():
    while True:
        data = input("Enter command: ")
        logger_.info(data)
        if data == "q":
            break

        if data == "l":
            # lights()
            for _ in range(100):
                fade_in(255, 0, 0)
                # fade_out(0, 0, 0)
                fade_in(255, 255, 0)
                fade_out(0, 255, 0)
                fade_in(0, 255, 255)
                fade_out(0, 0, 255)
                # fade_in(255, 0, 255)
                # fade_out(255, 255, 3)
                fade_in(255, 255, 255)
                fade_out(255, 0, 0)
                # fade_in(255, 0, 0)
                # fade_out(0, 0, 0)
                # fade_in(255, 0, 0)
                # fade_out(0, 0, 0)
                ArduinoSerial.reset_input_buffer()
                ArduinoSerial.reset_output_buffer()

        else:
            data = data.encode()
            logger_.info(data)
            ArduinoSerial.write(data)
            if ArduinoSerial:
                logger_.info(ArduinoSerial.readline())


if __name__ == "__main__":
    arduino = ArduinoController(baud_rate=115200)
    arduino.send_payload(X1=23, AUX6=1)
