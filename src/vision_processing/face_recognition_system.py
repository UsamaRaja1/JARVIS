import multiprocessing
import os
import time
from pathlib import Path
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
        self.min_x = 0
        self.max_x = 255
        self.min_y = 0
        self.max_y = 255
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
        self.detection_queue = multiprocessing.Queue()
        self.recognition_queue = multiprocessing.Queue()
        self.queues = {"detection_queue": self.detection_queue, "recognition_queue": self.recognition_queue}
        self.recognition_process = None
        self.detection_process = None
        self.stop_event = multiprocessing.Event()  # Event to signal stop
        self.is_running = False

    def recognize_faces_in_frame(self, data, arduino_controller, print_logs=False, threshold=0.55):
        face_location = data["face_locations"]
        x_axis = data.get("x_axis")
        y_axis = data.get("y_axis")
        names = []
        coordinates = []
        t = time.time()

        if face_location:
            person_encodings = fr.face_encodings(data["frame"], face_location)
            for i, _face_loc in enumerate(face_location):
                result = fr.compare_faces(self.encoded_images, person_encodings[i], tolerance=threshold)
                if True in result:
                    for j, val in enumerate(result):
                        if val:
                            name = self.images["names"][j]
                            names.append(name)
                            coordinates.append({name: {"x_axis": x_axis, "y_axis": y_axis}})
                    arduino_controller.lights_control({"green": 10, "red": 0})
                else:
                    name = "Unknown"
                    names.append(name)
                    coordinates.append({name: {"x_axis": None, "y_axis": None}})
                    arduino_controller.lights_control({"green": 0, "red": 10})

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

    def face_detection(self, cap: cv2.VideoCapture = None):
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

        prev_time = time.time()
        print_logs = False
        kx = 0
        ky = 0
        names = []
        face_locations = []
        flip = False

        recognition_queue = self.queues["recognition_queue"]
        detection_queue = self.queues["detection_queue"]
        face_detector = None

        try:
            options = mp.tasks.vision.FaceDetectorOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=get_face_detector_model_path()),
                min_detection_confidence=0.5,
            )
            face_detector = mp.tasks.vision.FaceDetector.create_from_options(options)

            while cap.isOpened() or self.stop_event.is_set():
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
                    face_locations = json_data.get("face_locations")

                if face_locations:
                    for i, face_loc in enumerate(face_locations):
                        y1, x2, y2, x1 = face_loc
                        y1, x2, y2, x1 = int(y1 / resize), int(x2 / resize), int(y2 / resize), int(x1 / resize)
                        cv2.putText(frame, names[i], (x1, y1 - 30), cv2.FONT_HERSHEY_COMPLEX, self.font_scale, self.color["green"], self.thickness)

                t1 = time.time()
                results = face_detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame))
                if print_logs:
                    logger_.info(f"Face detection time: {(time.time() - t1):.3f} sec")

                if results.detections:
                    for i, detection in enumerate(results.detections):
                        score = detection.categories[0].score
                        bounding_box = detection.bounding_box
                        x1, y1 = bounding_box.origin_x, bounding_box.origin_y
                        x2, y2 = x1 + bounding_box.width, y1 + bounding_box.height
                        facelocations.append([y1, x2, y2, x1])

                        cv2.rectangle(frame, (x1, y1), (x2, y2), self.color["green"], 1)
                        cv2.putText(frame, f"score: {(score):.2f}", (x1, y1 - 10), cv2.FONT_HERSHEY_COMPLEX, self.font_scale, self.color["green"], self.thickness)
                        cv2.putText(frame, f"FPS: {int(fps)}", (5, 25), cv2.FONT_HERSHEY_COMPLEX, self.font_scale, self.color["green"], self.thickness)

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
                    if flip:
                        recv = self.arduino_controller.send_payload(X1=self.max_x - x_axis, Y2=self.max_y - y_axis, AUX6=1)
                    else:
                        recv = self.arduino_controller.send_payload(X1=x_axis, Y2=self.max_y - y_axis, AUX6=1)
                    print(recv)
                    if score > 0.63:
                        kx = 0 if diff_x > 0 else 1
                        ky = 1 if diff_y > 0 else 0

                        if detection_queue.empty():
                            detection_queue.put({"frame": frame, "face_locations": facelocations, "x_axis": x_axis, "y_axis": y_axis})

                else:
                    steps = 3
                    if kx == 0:
                        x_axis += steps
                        if x_axis >= self.max_x:
                            x_axis = self.max_x
                            kx = 1
                    else:
                        x_axis -= steps
                        if x_axis <= self.min_x:
                            x_axis = self.min_x
                            kx = 0

                    if score > 0.6:
                        if ky == 0:
                            y_axis += steps
                            if y_axis >= self.max_y:
                                y_axis = self.max_y
                                ky = 1
                        else:
                            y_axis -= steps
                            if y_axis <= self.min_y:
                                y_axis = self.min_y
                                ky = 0
                    p = 0.9
                    if p != 1:
                        x_axis = int(px * (1 - p) + x_axis * p)
                        y_axis = int(py * (1 - p) + y_axis * p)

                    # logger.info(f"px {px}, py {py} |  x {x_axis}, y {y_axis}  |  prev-x {self.prev_x}, prev-y {self.prev_y}")

                    x_axis = min(self.max_x, max(self.min_x, x_axis))
                    y_axis = min(self.max_y, max(self.min_y, y_axis))
                    px, py = x_axis, y_axis
                    # self.arduino_controller.servo_move(x_axis, y_axis, p=1, print_logs=False)
                    if flip:
                        self.arduino_controller.send_payload(X1=self.max_x - x_axis, Y2=self.max_y - y_axis, AUX6=1)
                    else:
                        self.arduino_controller.send_payload(X1=x_axis, Y2=self.max_y - y_axis, AUX6=1)

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
            if face_detector is not None:
                face_detector.close()
            cap.release()
            cv2.destroyAllWindows()
            self.stop()

    def get_current_image(self):
        if not self.current_frame_queue.empty():
            return self.current_frame_queue.get()

    def run(self, in_background: bool = False, cap: cv2.VideoCapture = None):
        if not self.is_running:
            self.is_running = True
            self.stop_event.clear()
            try:
                if in_background:
                    if self.detection_process is None:
                        self.detection_process = multiprocessing.Process(target=self.face_detection, args=(cap,))
                    if not self.detection_process.is_alive():
                        self.detection_process.start()

                if self.recognition_process is None:
                    self.recognition_process = multiprocessing.Process(target=self.recognize_faces, args=(self.detection_queue, self.recognition_queue, self.arduino_controller))
                if not self.recognition_process.is_alive():
                    self.recognition_process.start()

                if not in_background:
                    self.face_detection(cap=cap)
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
                    self.recognition_process.join()
                except Exception:
                    if self.recognition_process.is_alive():
                        self.recognition_process.terminate()
                        self.recognition_process.join()
                    # self.recognition_process = None

            # Stop and clean up the detection process
            if self.detection_process is not None and self.detection_process.is_alive():
                logger_.info("Stopping face detection process...")
                try:
                    self.detection_process.join()
                except Exception:
                    if self.detection_process.is_alive():
                        self.detection_process.terminate()  # Force terminate if needed
                        self.detection_process.join()  # Wait for it to finish
                    # self.detection_process = None

            # Close and join queues
            for name, q in self.queues.items():
                try:
                    if q:
                        q.close()
                        q.join_thread()
                except Exception as e:
                    logger_.error(f"Failed to close {name}: {e}")

        except Exception as e:
            logger_.error(f"Error while stopping face recognition processes: {e}")


if __name__ == "__main__":
    arduino = ArduinoController()
    car = RCCarController(arduino)
    cap = car.connect_camera()
    face_recognition_system = FaceRecognitionSystem(arduino=arduino)
    face_recognition_system.run(cap=cap, in_background=True)
