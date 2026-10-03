import asyncio
import time

from src.actions_v2 import perform_action
from src.configs import BOT_NAME, FOLLOW_UP_WINDOW_SECONDS, IDLE_SLEEP_TIMEOUT_SECONDS, USER_NAME
from src.integrations.arduino_controller import ArduinoController
from src.integrations.rc_car import RCCarController
from src.utilz.logger import logger_
from src.utilz.modules import get_greetings
from src.vision_processing.face_recognition_system import FaceRecognitionSystem
from src.voice_processing.voice_assistant_v2 import assistant


async def greet_user():
    """Greets the user according to the time"""
    greeting = get_greetings()
    assistant.say(f"{greeting} {USER_NAME}! How can I assist you?")


async def jarvis(arduino=None, face_recognizer=None):
    rc_car = None
    try:
        arduino = arduino if arduino is not None else ArduinoController()
        face_recognizer = face_recognizer if face_recognizer else FaceRecognitionSystem(arduino)
        await greet_user()
        t = time.time()
        prev_query = ""
        timer = time.time()

        while True:
            wake_key = assistant.consume_wake_event()
            if wake_key and assistant.wake_from_sleep():
                timer = time.time()
                logger_.info(f"Jarvis woke from full sleep via double-{wake_key} press")

            if assistant.full_sleep:
                await asyncio.sleep(0.1)
                continue

            if utterance := assistant.get_committed_utterance():
                callback = False
                repeat_speech = False
                audio_data, user_name = utterance
                await assistant.transcribe_audio(callback, repeat_speech, assistant.offline_stt, audio_data=audio_data, user_name=user_name)

            query = assistant.text
            name = name if (name := assistant.user_name) else USER_NAME

            if time.time() - timer > IDLE_SLEEP_TIMEOUT_SECONDS:
                assistant.enter_sleep_mode()
                await asyncio.sleep(0.1)
                continue

            if BOT_NAME.lower() in query:
                timer = time.time()
                assistant.sleep = False

            if query.strip().lower() == "again":
                query = prev_query
            else:
                prev_query = query or prev_query

            # Perform Actions based on User Input
            if assistant.new_speech:
                assistant.new_speech = False
                command = query.strip().lower()

                if BOT_NAME.lower() in query or time.time() - t < FOLLOW_UP_WINDOW_SECONDS:
                    t = time.time()

                    if ("bye" in query and BOT_NAME.lower() in query) or "terminate" in query:
                        response = f"Understood. Shutting down. Goodbye {USER_NAME}."
                        assistant.say(response)
                        await asyncio.sleep(1)
                        break

                    elif ((("wifi" in command or "wi-fi" in command) and "camera" in command) or "car" in command) and any(
                        action in command for action in ("disconnect", "stop", "turn off", "deactivate")
                    ):
                        await asyncio.to_thread(face_recognizer.stop)
                        if rc_car:
                            rc_car.stop()
                            rc_car = None
                        assistant.say("WiFi camera and car controls stopped.")

                    elif ((("wifi" in command or "wi-fi" in command) and "camera" in command) or "car" in command) and any(action in command for action in ("connect", "start", "turn on", "activate")):
                        if rc_car:
                            assistant.say("The WiFi camera is already connected.")
                            continue

                        rc_car = RCCarController(arduino)
                        cap = await asyncio.to_thread(rc_car.connect_camera)

                        if cap:
                            face_recognizer.run(True, cap=cap, camera_control_queue=face_recognizer.camera_control_queue)
                            if face_recognizer.is_running:
                                rc_car.start_controls(
                                    camera_target_queue=face_recognizer.camera_control_queue,
                                    stop_event=face_recognizer.stop_event,
                                    telemetry_queue=face_recognizer.telemetry_queue,
                                )
                                assistant.say("WiFi camera connected. Face tracking and car controls are active.")
                            else:
                                rc_car.stop()
                                rc_car = None
                                assistant.say("The camera connected, but face tracking failed to start.")
                        else:
                            rc_car.stop()
                            rc_car = None
                            assistant.say("Failed to connect to WiFi camera.")

                    elif ("turn on" in command or "activate" in command.split()) and ("camera" in command or "detect" in command):
                        face_recognizer.run(True)
                        assistant.say("Turning on camera.")

                    elif ("turn off" in command or "deactivate" in command or "stop detection" in command or "stop face recognition" in command) and (
                        "camera" in command or "detect" in command or "face recognition" in command
                    ):
                        await asyncio.to_thread(face_recognizer.stop)
                        if not rc_car:
                            assistant.say("Face recognition stopped.")
                        else:
                            rc_car.stop()
                            rc_car = None
                            assistant.say("Face recognition, WiFi camera, and car controls stopped.")

                    elif "go to" in query and "sleep" in query:
                        t = time.time() - FOLLOW_UP_WINDOW_SECONDS - 10
                        response = "Sure, if you need anything, just call my name."
                        assistant.say(response)
                        await asyncio.sleep(5)
                        assistant.enter_sleep_mode()

                    else:
                        await perform_action(query, arduino, face_recognizer, assistant, name)

                else:
                    logger_.info(f"You are in sleep mode, say {BOT_NAME} to turn on commands")

    except Exception as e:
        logger_.error(f"Error in jarvis: {e}")
        assistant.say("An unexpected error occurred. I'm shutting down now.")
    finally:
        await asyncio.to_thread(face_recognizer.stop)
        if rc_car:
            rc_car.stop()
        assistant.stop_listener()


if __name__ == "__main__":
    asyncio.run(jarvis())
