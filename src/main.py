# import threading
import asyncio
import subprocess

from src.integrations.arduino_controller import ArduinoController
from src.jarvis import jarvis
from src.vision_processing.face_recognition_system import FaceRecognitionSystem


# Function to run a script using subprocess
def run_script(script_name):
    subprocess.run(["python", script_name])


if __name__ == "__main__":
    # Uncomment to run scripts in threads if needed
    # script1_thread = threading.Thread(target=run_script, args=("face_recognition_system.py",))
    # script2_thread = threading.Thread(target=run_script, args=("jarvis.py",))
    # script1_thread.start()
    # script2_thread.start()
    # script1_thread.join()
    # script2_thread.join()
    # print("Both scripts have finished executing.")

    # Initialize the Arduino controller
    arduino_controller = ArduinoController()
    face_recognizer = FaceRecognitionSystem(arduino_controller)

    # Initialize queues for communication between processes
    # recognition_queue = multiprocessing.Queue()
    # detection_queue = multiprocessing.Queue()
    # queues = {'queue': recognition_queue, 'data_queue': detection_queue}

    # Start the recognition and jarvis processes
    # recognition_process = multiprocessing.Process(target=recognize_faces, args=(queue, data_queue, arduino_controller))
    # # jarvis_process = multiprocessing.Process(target=jarvis, args=(arduino_controller,))
    # face_detection_process = multiprocessing.Process(target=face_detection, args=(queues, arduino_controller))

    face_recognizer.run(True)

    # recognition_process.start()
    # # jarvis_process.start()
    # face_detection_process.start()

    try:
        # Start face detection and keep it running
        # face_detection(queues, arduino_controller)
        asyncio.run(jarvis(arduino_controller, face_recognizer))

        # Signal the recognition process to stop
        # recognition_queue.put(None)
        # recognition_process.join()
        # # jarvis_process.join()
        # face_detection_process.join()

        # Reset Arduino lights to off
        arduino_controller.lights_control({"red": 0, "green": 0, "blue": 0})

    except Exception as e:
        print(f"Error: {e}")
        # Ensure the recognition process is stopped in case of an error
        # recognition_queue.put(None)
        # recognition_process.join()
        # # jarvis_process.join()
        # face_detection_process.join()
