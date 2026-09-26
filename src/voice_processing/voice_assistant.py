import asyncio
import datetime
import os
import threading
import time

import librosa
import numpy as np
import pyaudio
import torch

from src.configs import BOT_NAME, VOICE_SAMPLE_DIR
from src.integrations.arduino_controller import ArduinoController
from src.utilz.logger import logger_
from src.voice_processing.speech_models import TTS, listen
from src.voice_processing.voice_recognition import VoiceRecognition

torch.set_num_threads(1)

logger_.info("Loading Silero-VAD model")
model, utils = torch.hub.load(repo_or_dir="snakers4/silero-vad", model="silero_vad", force_reload=False)
(get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils


class VoiceAssistant:
    def __init__(self, model, listen, tts, voice_recognizer: VoiceRecognition = None, arduino: ArduinoController = None, logger=None, bot_name=None, offline_stt=False):
        self.model = model
        self._listen = listen
        self.tts = tts()
        self.voice_recognizer = voice_recognizer
        self.user_name = None
        self.bot_name = bot_name if bot_name else BOT_NAME
        self.offline_stt = offline_stt
        self.arduino = arduino
        self.vad_iterator = VADIterator(model=model)

        self.format = pyaudio.paInt16
        self.channels = 1
        self.sample_rate = 16000
        self.chunk = int(self.sample_rate / 10)
        self.num_samples = 512
        self.audio_data = []

        self.recording_started = False
        self.continue_recording = True
        self.transcription_completed = False
        self.speech_committed = False
        self.text = ""
        self._logger = logger
        self.max_recording_time = 10  # in sec
        self.is_speaking = False
        self.prev_recognition_time = 0

        self.interrupted = asyncio.Event()  # asyncio event for interruptions
        self.tts_task = None
        self.transcription_task = None
        self.recognition_task = None

        self.audio = None
        self.audio_stream = None
        self.start_stream()
        self.save_bot_audio_sample(VOICE_SAMPLE_DIR)

    def save_bot_audio_sample(self, samples_dir):
        text = f"Hello, my name is {self.bot_name}, your intelligent voice assistant. I'm here to assist you with tasks and answer your queries."
        filename = os.path.join(samples_dir, f"{self.bot_name.lower()}.wav")
        os.makedirs(samples_dir, exist_ok=True)
        self.tts.save_to_file(text, filename)

    async def listen(self, callback=None, allow_interruption=False, speech_commit_threshold=1.0, interrupt_threshold=0.5, vad_threshold=0.4, repeat_speech=False, loop=False, recognition_freq=2.0):
        self.continue_recording = True
        self.recording_started = False
        speech_detected = False
        data = []
        t = time.time()
        st = time.time()
        t2 = time.time()

        if not loop:
            self.start_stream()

        while self.continue_recording:
            audio_chunk = self.audio_stream.read(self.num_samples)
            data.append(audio_chunk)

            audio_int16 = np.frombuffer(audio_chunk, np.int16)
            audio_float32 = self.int2float(audio_int16)
            confidence = self.model(torch.from_numpy(audio_float32), self.sample_rate).item()
            if not self.recording_started:
                st = time.time()

            if confidence > vad_threshold and time.time() - st < self.max_recording_time:
                t = time.time()
                if not speech_detected:
                    t2 = time.time()
                    speech_detected = True

                if not self.recording_started and not self.tts.is_playing:
                    data = data[-10:]
                    self.recording_started = True
                    self.speech_committed = False
                    self.interrupted.clear()
                    self.log_info("speech_detected")
                    st = time.time()
                    t2 = time.time()
                    # Cancel ongoing TTS task if speech is detected
                    if self.tts_task and not self.tts_task.done():
                        logger_.info("Interrupting TTS due to detected speech")
                        self.tts.stop()
                        self.tts_task.cancel()
                        self.is_speaking = False

                    if self.transcription_task and not self.transcription_task.done():
                        logger_.info("Canceling transcription task due to new speech detection")
                        self.transcription_task.cancel()

                # TODO: fix the audio capture and assistant interruption
                elif self.is_speaking:
                    if allow_interruption and time.time() - t2 > interrupt_threshold:
                        audio_int16_list = [np.frombuffer(audio_chunk, np.int16) for audio_chunk in data[-60:]]
                        audio_data = np.concatenate(audio_int16_list)
                        # print(len(data))
                        # print(f'{time.time():.3f} interruption check 1')

                        if time.time() - self.prev_recognition_time > recognition_freq:
                            self.prev_recognition_time = time.time()
                            if self.recognition_task and not self.recognition_task.done():
                                self.log_info("cancelling voice recognition task")
                                self.recognition_task.cancel()
                            self.log_info("Creating voice recognition_task")
                            self.recognition_task = asyncio.create_task(self.is_bot_speaking(audio_data, 0.5))
                            # if not is_bot:
                            #     self.log_info("speech_interrupted")
                            #     if self.tts_task and not self.tts_task.done():
                            #         logger.info(f"Speech interrupted, stopping TTS")
                            #         self.tts.stop()
                            #         self.tts_task.cancel()
                            #         self.is_speaking = False
                            #
                            #     self.speech_committed = False
                            #     data = prev_data + data
                            #
                            #     if self.transcription_task and not self.transcription_task.done():
                            #         logger.info("Canceling transcription task due to new speech detection")
                            #         self.transcription_task.cancel()

            else:
                if time.time() - t > speech_commit_threshold and self.recording_started:
                    self.log_info("speech_committed")
                    audio_int16_list = [np.frombuffer(audio_chunk, np.int16) for audio_chunk in data]
                    self.audio_data = np.concatenate(audio_int16_list)
                    self.speech_committed = True
                    self.recording_started = False
                    self.interrupted.clear()
                    speech_detected = False

                    if self.voice_recognizer:
                        results = self.voice_recognizer.recognize_voice(self.audio_data.copy())
                        if name := results["name"]:
                            self.user_name = name
                        else:
                            self.user_name = ""

                    self.transcription_task = asyncio.create_task(self.transcribe_audio(callback, repeat_speech, self.offline_stt))
                    # await self.transcription_task

                    if not loop:
                        # self.close_stream()
                        return self.text

    async def transcribe_audio(self, callback, repeat_speech, offline_stt=False):
        try:
            self.text = self._listen(audio=self.audio_data, offline_stt=offline_stt)

            if self.text:
                self.log_info(f"{name if (name := self.user_name) else 'User'}: {self.text}")
                if repeat_speech:
                    await self.say(self.text)

                if (self.bot_name in self.text and "bye" in self.text) or "terminate" in self.text:
                    self.continue_recording = False
                    self.close_stream()
                    if self.tts_task and not self.tts_task.done():
                        self.tts_task.cancel()
                    if self.transcription_task and not self.transcription_task.done():
                        self.transcription_task.cancel()

                if callback:
                    callback(self.text)

        except asyncio.CancelledError:
            logger_.info("Transcription task was interrupted and canceled.")
        except Exception as e:
            logger_.error(f"Error occurred while transcribing audio: {e}")

    async def say(self, text, rate=190):
        if not asyncio.iscoroutinefunction(self.tts.say):
            logger_.error(f"tts.say must be a coroutine function. Found: {type(self.tts.say)}")
            raise TypeError("tts.say must be a coroutine function")

        if self.is_speaking:
            self.tts.stop()
            if self.tts_task and not self.tts_task.done():
                logger_.info("Cancelling tts task")
                self.tts_task.cancel()

        self.is_speaking = True
        logger_.info("Creating a new TTS task")
        self.tts_task = asyncio.create_task(self.tts.say(text))
        self.log_info(f"{self.bot_name}: {text}")
        # await self.tts_task
        # self.is_speaking = False

    def is_user_authorized(self):
        return self.user_name.lower() == os.getlogin().lower()

    def identify_gender(self, audio_file):
        # Load the audio file
        y, sr = librosa.load(audio_file, sr=None)

        # Extract the fundamental frequency (F0) using librosa's pitch tracking
        pitches, _magnitudes = librosa.piptrack(y=y, sr=sr)

        # Compute the mean pitch (filter out zeros)
        pitches = pitches[pitches > 0]  # Remove zero values
        mean_pitch = np.mean(pitches) if len(pitches) > 0 else 0

        # Classify gender based on pitch range
        if mean_pitch < 165:  # Threshold for male/female classification
            return "Male"
        else:
            return "Female"

    def start_listener(self, **kwargs):
        audio_thread = threading.Thread(target=self.listen, kwargs=kwargs)
        try:
            audio_thread.start()
            audio_thread.join()  # Wait for the audio thread to finish
            return self.text  # Return the transcribed text
        except Exception as e:
            logger_.error(f"Error in listener: {e}")
            return None

    async def is_bot_speaking(self, audio_data, threshold=0.5):
        if self.voice_recognizer:
            results = self.voice_recognizer.recognize_voice(audio_data, threshold=threshold, tmp_file="test.wav")
            print(results)
            is_bot = results["name"].lower() == self.bot_name.lower()
            if not is_bot:
                self.log_info("speech_interrupted")
                if self.tts_task and not self.tts_task.done():
                    logger_.info("Speech interrupted, stopping TTS")
                    self.tts.stop()
                    self.tts_task.cancel()
                    self.is_speaking = False

                self.speech_committed = False
                # data = prev_data + data

                if self.transcription_task and not self.transcription_task.done():
                    logger_.info("Canceling transcription task due to new speech detection")
                    self.transcription_task.cancel()

    def start_stream(self):
        if self.audio_stream is not None and self.audio_stream.is_active():
            # logger.info('Audio stream already started')
            return

        self.audio = pyaudio.PyAudio()
        self.audio_stream = self.audio.open(format=self.format, channels=self.channels, rate=self.sample_rate, input=True, frames_per_buffer=self.chunk)
        logger_.info("Audio streaming started")

    def close_stream(self):
        self.audio_stream.stop_stream()
        self.audio_stream.close()
        self.audio.terminate()

    @staticmethod
    def int2float(sound):
        abs_max = np.abs(sound).max()
        sound = sound.astype("float32")
        if abs_max > 0:
            sound *= 1 / 32768
        sound = sound.squeeze()  # depends on the use case
        return sound

    def log_info(self, text):
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M:%S.%f")
        self._logger.info(f"{current_time} - {text}")


# class Listener:
#     def __init__(self, model, whisper, listen, say, format=pyaudio.paInt16, channels=1, sample_rate=16000, chunk=None):
#         self.model = model
#         self.whisper = whisper
#         self.listen = listen
#         self.say = say
#
#         self.format = format
#         self.channels = channels
#         self.sample_rate = sample_rate
#         self.chunk = chunk if chunk else int(sample_rate / 10)
#
#         self.num_samples = 512
#         self.audio_data = []
#         self.continue_recording = True
#         self.interrupted = asyncio.Event()  # asyncio event for interruptions
#         self.transcription_task = None  # To manage ongoing transcription
#         self.speech_committed = False
#         self.text = ''
#         self.audio = None
#         self.audio_stream = None
#         self.start_stream()
#
#     async def get_audio(self, callback=None, allow_interruption=False, speech_commit_threshold=1.0,
#                         interrupt_threshold=0.5, vad_threshold=0.3, repeat_speech=False, loop=False):
#         self.continue_recording = True
#         self.recording_started = False
#         data = []
#         t = time.time()
#
#         while self.continue_recording:
#             audio_chunk = self.audio_stream.read(self.num_samples)
#             data.append(audio_chunk)
#
#             audio_int16 = np.frombuffer(audio_chunk, np.int16)
#             audio_float32 = self.int2float(audio_int16)
#
#             new_confidence = self.model(torch.from_numpy(audio_float32), self.sample_rate).item()
#
#             if new_confidence > vad_threshold:
#                 t = time.time()
#                 if not self.recording_started:
#                     data = data[-10:]
#                     self.recording_started = True
#                     self.speech_committed = False
#                     self.interrupted.clear()
#                     logger.info("speech_detected")
#
#                     # Cancel ongoing transcription if allowed
#                     if allow_interruption and self.transcription_task and not self.transcription_task.done():
#                         logger.info("Interrupting ongoing transcription...")
#                         self.transcription_task.cancel()
#                         await self.transcription_task
#
#                 elif self.speech_committed:
#                     if allow_interruption and time.time() - t > interrupt_threshold:
#                         logger.info("speech_interrupted")
#                         self.interrupted.set()
#                         self.speech_committed = False
#                         data = []
#
#             else:
#                 if time.time() - t > speech_commit_threshold and self.recording_started:
#                     logger.info("speech_committed")
#                     audio_int16_list = [np.frombuffer(audio_chunk, np.int16) for audio_chunk in data]
#                     self.audio_data = np.concatenate(audio_int16_list)
#                     self.speech_committed = True
#                     self.recording_started = False
#                     self.interrupted.clear()
#
#                     # Start transcription task
#                     self.transcription_task = asyncio.create_task(self.transcribe_audio(callback, repeat_speech))
#                     if not loop:
#                         await self.transcription_task
#                         return self.text
#
#             await asyncio.sleep(0.01)  # Non-blocking delay
#
#     async def transcribe_audio(self, callback, repeat_speech):
#         try:
#             logger.info("Transcribing audio...")
#             self.text = self.listen(audio=self.audio_data) or self.whisper(self.audio_data).get('text')
#
#             if self.text:
#                 logger.info(f"Text: {self.text}")
#                 if repeat_speech:
#                     self.say(self.text)
#
#                 if 'jarvis' in self.text and any(word in self.text for word in ['goodbye', 'bye']):
#                     self.continue_recording = False
#                     self.close_stream()
#
#                 if callback:
#                     callback(self.text)
#         except asyncio.CancelledError:
#             logger.info("Transcription task was interrupted and canceled.")
#         except Exception as e:
#             logger.error(f"Error occurred while transcribing audio: {e}")
#
#     def start_stream(self):
#         self.audio = pyaudio.PyAudio()
#         self.audio_stream = self.audio.open(format=self.format,
#                                             channels=self.channels,
#                                             rate=self.sample_rate,
#                                             input=True,
#                                             frames_per_buffer=self.chunk)
#         logger.info("Audio streaming started")
#
#     def close_stream(self):
#         self.audio_stream.stop_stream()
#         self.audio_stream.close()
#         self.audio.terminate()
#
#     @staticmethod
#     def int2float(sound):
#         abs_max = np.abs(sound).max()
#         sound = sound.astype("float32")
#         if abs_max > 0:
#             sound *= 1 / 32768
#         return sound

recognizer = VoiceRecognition()
assistant = VoiceAssistant(model=model, listen=listen, tts=TTS, voice_recognizer=recognizer, logger=logger_, offline_stt=True, bot_name=BOT_NAME)

if __name__ == "__main__":
    asyncio.run(assistant.listen(loop=True, repeat_speech=True, speech_commit_threshold=1.0, interrupt_threshold=0.5))
