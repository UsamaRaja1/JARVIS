import asyncio
import time

from src.actions import perform_action
from src.configs import BOT_NAME, USER_NAME
from src.integrations.arduino_controller import ArduinoController
from src.utilz.logger import logger_
from src.utilz.modules import get_greetings
from src.vision_processing.face_recognition_system import FaceRecognitionSystem
from src.voice_processing.voice_assistant import assistant

# from playsound import playsound


# playsound('../audios/jarvis_plug_in.mp3')


async def greet_user():
    """Greets the user according to the time"""
    greeting = get_greetings()
    await assistant.say(f"{greeting} {USER_NAME}! I am {BOT_NAME}. How can I assist you?")


async def jarvis(arduino=None, face_recognizer=None):
    try:
        arduino = arduino if arduino is not None else ArduinoController()
        face_recognizer = face_recognizer if face_recognizer else FaceRecognitionSystem(arduino)
        await greet_user()
        sleep_time = 90
        t = time.time()
        prev_query = ""

        while True:
            # Run the listener and task concurrently
            listener_task = asyncio.create_task(assistant.listen(allow_interruption=True, vad_threshold=0.45))

            # Wait for both tasks to complete
            await asyncio.gather(listener_task, return_exceptions=True)

            query = assistant.text
            name = name if (name := assistant.user_name) else USER_NAME

            # Perform Actions based on User Input
            if query and query != prev_query:
                prev_query = query
                if BOT_NAME.lower() in query or time.time() - t < sleep_time:
                    t = time.time()
                    if ("bye" in query and BOT_NAME.lower() in query) or "terminate" in query:
                        response = f"Goodbye {USER_NAME}."
                        print(f"{BOT_NAME}: {response}")
                        await assistant.say(response)
                        await asyncio.sleep(1)
                        if face_recognizer is not None:
                            face_recognizer.stop()
                        break
                    elif ("turn on" in query or "activate" in query.split()) and ("camera" in query or "detect" in query):
                        face_recognizer.run(True)
                        await assistant.say("Turning on camera.")
                    elif ("turn off" in query or "deactivate" in query) and ("camera" in query or "detect" in query):
                        face_recognizer.stop()
                        await assistant.say("Turning off camera.")
                    elif "go to" in query and "sleep" in query:
                        t = time.time() - sleep_time - 10
                        response = f"Sure, if you need anything, just call my name. Goodbye {USER_NAME}."
                        print(f"{BOT_NAME}: {response}")
                        await assistant.say(response)
                    else:
                        await perform_action(query, arduino, face_recognizer, assistant, name)
                else:
                    logger_.info(f"You are in sleep mode, say {BOT_NAME} to turn on commands")

    except Exception as e:
        logger_.error(f"Error in jarvis: {e}")


if __name__ == "__main__":
    asyncio.run(jarvis())
