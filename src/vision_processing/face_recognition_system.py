import contextlib
import multiprocessing
import os
import time
from pathlib import Path
from queue import Empty, Full
from urllib.request import urlretrieve

import cv2
import face_recognition as fr
import mediapipe as mp

from src.configs import DATA_DIR, IMAGE_ENCODING_DIR, IMAGE_SAMPLE_DIR
from src.integrations.arduino_controller import ArduinoController
from src.integrations.rc_car import RCCarController
from src.modules.video_capture import get_video_capture
from src.utilz.logger import logger_
from src.utilz.modules import encode_images, load_images

FACE_DETECTOR_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"


def get_face_detector_model_path():
    model_path = Path(os.getenv("FACE_DETECTOR_MODEL_PATH", Path(DATA_DIR) / "models" / "blaze_face_short_range.tflite"))
    if model_path.is_file():
        return str(model_path)

    model_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = model_path.with_suffix(".tmp")
    logger_.info(f"Downloading MediaPipe face detector model to: {model_path}")
    try:
        urlretrieve(FACE_DETECTOR_MODEL_URL, temporary_path)
        temporary_path.replace(model_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return str(model_path)


class FaceRecognitionSystem:
    def __init__(self, arduino=None, images_dir=None, encoding_dir=None):
        # Keep tracking and searching away from the camera mount's hard stops.
        self.min_x = 35
        self.max_x = 220
        self.min_y = 0
        self.max_y = 200
        self.font_scale = 0.5
        self.thickness = 2
        self.color = {"blue": (255, 0, 0), "green": (0, 255, 0), "red": (0, 0, 255), "white": (255, 255, 255)}

        self.images_dir = images_dir if images_dir else IMAGE_SAMPLE_DIR
        self.encoding_dir = encoding_dir if encoding_dir else IMAGE_ENCODING_DIR
        self.images = load_images(self.images_dir)
        self.encoded_images = encode_images(self.images, self.encoding_dir)
        self.person_data = {}
        self.current_frame_queue = multiprocessing.Queue(maxsize=1)
        self.arduino_controller = arduino if arduino else ArduinoController()
        self.detection_queue = None
        self.recognition_queue = None
        self.queues = {}
        self._create_worker_queues()
        self.recognition_process = None
        self.detection_process = None
        self.stop_event = multiprocessing.Event()  # Event to signal stop
        self.camera_control_queue = multiprocessing.Queue(maxsize=1)
        self.telemetry_queue = multiprocessing.Queue(maxsize=1)
        self.is_running = False

    @staticmethod
    def _move_toward(current, target, step=3):
        if abs(target - current) <= step:
            return target
        return current + step if target > current else current - step

    @staticmethod
    def _nearest_position_index(positions, x, y):
        return min(range(len(positions)), key=lambda i: (positions[i][0] - x) ** 2 + (positions[i][1] - y) ** 2)

    def _create_worker_queues(self):
        self.detection_queue = multiprocessing.Queue()
        self.recognition_queue = multiprocessing.Queue()
        self.queues = {"detection_queue": self.detection_queue, "recognition_queue": self.recognition_queue}

    def _clear_camera_targets(self):
        while True:
            try:
                self.camera_control_queue.get_nowait()
            except Empty:
                return

    def recognize_faces_in_frame(self, data, arduino_controller, print_logs=False, threshold=0.55):
        face_location = data["face_locations"]
        names = []
        t = time.time()

        if face_location:
            person_encodings = fr.face_encodings(data["frame"], face_location)
            for person_encoding in person_encodings:
                distances = fr.face_distance(self.encoded_images, person_encoding)
                best_index = distances.argmin() if len(distances) else None
                names.append(self.images["names"][best_index] if best_index is not None and distances[best_index] <= threshold else "Unknown")

            known_face = any(name != "Unknown" for name in names)
            arduino_controller.lights_control({"green": 10 if known_face else 0, "red": 0 if known_face else 10})
            face_location = face_location[: len(names)]

        if print_logs:
            logger_.info(f"Face recognition time: {(time.time() - t):.3f} sec")

        return face_location, names

    def recognize_faces(self, detection_queue, recognition_queue, arduino_controller):
        data = None
        while not self.stop_event.is_set():  # Use Event to stop the process
            try:
                data = detection_queue.get()
            except:
                continue

            if data is None:
                arduino_controller.lights_control({"red": 0, "green": 0, "blue": 0})
                break

            faceLocations, names = self.recognize_faces_in_frame(data, arduino_controller)
            recognition_queue.put({"face_locations": faceLocations, "names": names})

    @staticmethod
    def _send_camera_target(camera_control_queue, x, y):
        """Publish only the newest target so tracking never blocks on stale frames."""
        try:
            camera_control_queue.put_nowait((x, y))
        except Full:
            with contextlib.suppress(Empty):
                camera_control_queue.get_nowait()
            with contextlib.suppress(Full):
                camera_control_queue.put_nowait((x, y))

    def face_detection(self, cap: cv2.VideoCapture = None, camera_control_queue=None):
        resize = 1
        if cap is None:
            cap = get_video_capture()

        if cap is None:
            return

        cap.set(3, 800)  # width
        cap.set(4, 720)  # height
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) * resize)
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) * resize)
        logger_.info(f"frame width: {frame_width}, height: {frame_height}")
        cv2.namedWindow("Face Recognition", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Face Recognition", 680, 520)

        cam_cx = int(frame_width / 2)
        cam_cy = int(frame_height / 2)
        fx = cam_cx / 6
        fy = cam_cy / 6
        x_axis, y_axis = 127, 127
        px, py = x_axis, y_axis

        detector_options = mp.tasks.vision.FaceDetectorOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=get_face_detector_model_path()),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            min_detection_confidence=0.5,
        )
        face_detector = mp.tasks.vision.FaceDetector.create_from_options(detector_options)

        prev_time = time.time()
        print_logs = False
        names = []
        flip = False
        scan_positions = (
            (127, 80),
            (75, 80),
            (180, 80),
            (127, 120),
            (75, 120),
            (180, 120),
        )
        scan_index = 0
        scan_hold_until = 0.0
        was_tracking = False
        telemetry = {}

        recognition_queue = self.queues["recognition_queue"]
        detection_queue = self.queues["detection_queue"]

        try:
            while cap.isOpened() and not self.stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    break

                frame_org = cv2.flip(frame, 1) if flip else frame

                frame = frame_org.copy()
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                curr_time = time.time()
                fps = 1 / (curr_time - prev_time)
                prev_time = curr_time

                x_min = frame_width
                y_min = frame_height
                x_max = 0
                y_max = 0
                score = 0
                facelocations = []

                if not recognition_queue.empty():
                    json_data = recognition_queue.get()
                    names = json_data.get("names")

                try:
                    while True:
                        telemetry = self.telemetry_queue.get_nowait()
                except Empty:
                    pass

                t1 = time.time()
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                results = face_detector.detect_for_video(mp_image, time.monotonic_ns() // 1_000_000)
                if print_logs:
                    logger_.info(f"Face detection time: {(time.time() - t1):.3f} sec")

                if results.detections:
                    was_tracking = True
                    for i, detection in enumerate(results.detections):
                        score = detection.categories[0].score
                        bbox = detection.bounding_box
                        x1, y1 = bbox.origin_x, bbox.origin_y
                        x2, y2 = x1 + bbox.width, y1 + bbox.height
                        facelocations.append([y1, x2, y2, x1])

                        label = names[i] if len(names) == len(results.detections) else "Analyzing..."
                        label = f"{label}  {score:.0%}"
                        (label_width, label_height), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, self.font_scale, 1)
                        label_y = max(label_height + 8, y1)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), self.color["green"], 2)
                        cv2.rectangle(frame, (x1, label_y - label_height - 8), (x1 + label_width + 12, label_y), (20, 20, 20), -1)
                        cv2.putText(frame, label, (x1 + 6, label_y - 5), cv2.FONT_HERSHEY_SIMPLEX, self.font_scale, self.color["white"], 1, cv2.LINE_AA)

                        x_min = min(x_min, x1)
                        y_min = min(y_min, y1)
                        x_max = max(x_max, x2)
                        y_max = max(y_max, y2)

                    x, y = int((x_min + x_max) / 2), int((y_min + y_max) / 2)
                    diff_x, diff_y = (x - cam_cx), (y - cam_cy)
                    adj_x, adj_y = int(diff_x / fx), -int(diff_y / fy)

                    x_axis += adj_x
                    y_axis += adj_y

                    if print_logs:
                        logger_.info(f"cam_cx: {cam_cx}, cam_cy: {cam_cy}, x: {x}, y: {y}, adj_x: {adj_x}, adj_y: {adj_y}, ", f"x_axis: {x_axis}, y_axis: {y_axis}")
                    p = 0.9
                    if p != 1:
                        x_axis = int(px * (1 - p) + x_axis * p)
                        y_axis = int(py * (1 - p) + y_axis * p)

                    # logger.info(f"px {px}, py {py} |  x {x_axis}, y {y_axis}  |  prev-x {self.prev_x}, prev-y {self.prev_y}")

                    x_axis = min(self.max_x, max(self.min_x, x_axis))
                    y_axis = min(self.max_y, max(self.min_y, y_axis))
                    px, py = x_axis, y_axis
                    # self.arduino_controller.servo_move(x_axis, y_axis, p=0.8, print_logs=False)
                    target_x = self.max_x - x_axis if flip else x_axis
                    target_y = self.max_y - y_axis
                    if camera_control_queue is not None:
                        self._send_camera_target(camera_control_queue, target_x, target_y)
                        recv = None
                    else:
                        recv = self.arduino_controller.send_payload(X1=target_x, Y2=target_y, AUX6=1)
                    if recv:
                        print(recv)
                    if score > 0.63:
                        scan_hold_until = 0.0
                        if detection_queue.empty():
                            detection_queue.put({"frame": frame, "face_locations": facelocations, "x_axis": x_axis, "y_axis": y_axis})

                else:
                    if was_tracking:
                        scan_index = self._nearest_position_index(scan_positions, x_axis, y_axis)
                        scan_hold_until = 0.0
                        was_tracking = False
                    target_x, target_y = scan_positions[scan_index]
                    print(target_x, target_y)
                    x_axis = self._move_toward(x_axis, target_x)
                    y_axis = self._move_toward(y_axis, target_y)
                    if (x_axis, y_axis) == (target_x, target_y):
                        if not scan_hold_until:
                            scan_hold_until = time.monotonic() + 0.7
                        elif time.monotonic() >= scan_hold_until:
                            scan_index = (scan_index + 1) % len(scan_positions)
                            scan_hold_until = 0.0

                    x_axis = min(self.max_x, max(self.min_x, x_axis))
                    y_axis = min(self.max_y, max(self.min_y, y_axis))
                    px, py = x_axis, y_axis
                    # self.arduino_controller.servo_move(x_axis, y_axis, p=1, print_logs=False)
                    target_x = self.max_x - x_axis if flip else x_axis
                    target_y = self.max_y - y_axis
                    if camera_control_queue is not None:
                        self._send_camera_target(camera_control_queue, target_x, target_y)
                    else:
                        self.arduino_controller.send_payload(X1=target_x, Y2=target_y, AUX6=1)

                rc_data = f"  |  RC DATA: {telemetry['message']}" if telemetry.get("message") else ""
                status = f"FPS {int(fps)}  |  {'TRACKING' if results.detections else 'SEARCHING'}{rc_data}"
                (status_width, _), _ = cv2.getTextSize(status, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(frame, (8, 8), (status_width + 24, 36), (20, 20, 20), -1)
                cv2.putText(frame, status, (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.color["white"], 1, cv2.LINE_AA)

                if not self.current_frame_queue.empty():
                    self.current_frame_queue.get_nowait()  # Remove the old frame

                self.current_frame_queue.put(frame.copy(), block=False)

                cv2.imshow("Face Recognition", frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    cv2.destroyAllWindows()
                    break

        except KeyboardInterrupt:
            logger_.info("User interrupt: Stopping Face Detection")

        except Exception as e:
            logger_.error(f"Face detection error: {e}")
        finally:
            self.stop_event.set()
            face_detector.close()
            cap.release()
            cv2.destroyAllWindows()

    def get_current_image(self):
        if not self.current_frame_queue.empty():
            return self.current_frame_queue.get()

    def run(self, in_background: bool = False, cap: cv2.VideoCapture = None, camera_control_queue=None):
        if not self.is_running:
            self.is_running = True
            self.stop_event.clear()
            self._clear_camera_targets()
            try:
                if in_background:
                    if self.detection_process is None:
                        self.detection_process = multiprocessing.Process(target=self.face_detection, args=(cap, camera_control_queue))
                    if not self.detection_process.is_alive():
                        self.detection_process.start()

                if self.recognition_process is None:
                    self.recognition_process = multiprocessing.Process(target=self.recognize_faces, args=(self.detection_queue, self.recognition_queue, self.arduino_controller))
                if not self.recognition_process.is_alive():
                    self.recognition_process.start()

                if not in_background:
                    self.face_detection(cap=cap, camera_control_queue=camera_control_queue)
                    self.detection_queue.put(None)
                    self.stop_event.set()
                    self.stop()

            except Exception as e:
                logger_.error(f"Error in run: {e}")
                self.stop()

    def stop(self):
        if not self.is_running:
            return

        self.stop_event.set()  # Signal the stop event
        self.is_running = False

        try:
            logger_.info("Stopping Face Detection")
            if self.detection_queue:
                self.detection_queue.put(None)

            # Stop and clean up the recognition process
            if self.recognition_process is not None and self.recognition_process.is_alive():
                logger_.info("Stopping face recognition process...")
                try:
                    self.recognition_process.join(timeout=2)
                    if self.recognition_process.is_alive():
                        self.recognition_process.terminate()
                        self.recognition_process.join(timeout=2)
                except Exception:
                    if self.recognition_process.is_alive():
                        self.recognition_process.terminate()
                        self.recognition_process.join(timeout=2)
                    # self.recognition_process = None

            # Stop and clean up the detection process
            if self.detection_process is not None and self.detection_process.is_alive():
                logger_.info("Stopping face detection process...")
                try:
                    self.detection_process.join(timeout=2)
                    if self.detection_process.is_alive():
                        self.detection_process.terminate()
                        self.detection_process.join(timeout=2)
                except Exception:
                    if self.detection_process.is_alive():
                        self.detection_process.terminate()  # Force terminate if needed
                        self.detection_process.join(timeout=2)  # Wait for it to finish
                    # self.detection_process = None

            # Close and join queues
            for name, q in self.queues.items():
                try:
                    if q:
                        # Workers may have been terminated with buffered data. Waiting for
                        # their feeder threads here can block Jarvis forever.
                        q.cancel_join_thread()
                        q.close()
                except Exception as e:
                    logger_.error(f"Failed to close {name}: {e}")

            self.recognition_process = None
            self.detection_process = None
            self._create_worker_queues()

        except Exception as e:
            logger_.error(f"Error while stopping face recognition processes: {e}")


if __name__ == "__main__":
    arduino = ArduinoController()
    car = RCCarController(arduino)
    cap = car.connect_camera()
    face_recognition_system = FaceRecognitionSystem(arduino=arduino)
    face_recognition_system.run(cap=cap, in_background=True)
