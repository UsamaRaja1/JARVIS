import asyncio
import contextlib
import getpass
import os
import queue
import threading
import time

import numpy as np
import pyaudio
import torch

from src.configs import BOT_NAME, VOICE_SAMPLE_DIR
from src.integrations.arduino_controller import ArduinoController
from src.modules.keyboard_listener import KeyboardListener
from src.utilz.logger import logger_
from src.voice_processing.speech_models import TTS2, listen
from src.voice_processing.voice_recognition import VoiceRecognition

torch.set_num_threads(1)

logger_.info("Loading Silero-VAD model")
model, utils = torch.hub.load(repo_or_dir="snakers4/silero-vad", model="silero_vad", force_reload=False)
(get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils
vad_iterator = VADIterator(model)


class VoiceAssistant:
    def __init__(self, model, listen, tts, voice_recognizer: VoiceRecognition = None, arduino: ArduinoController = None, logger=None, bot_name=None, offline_stt=False):
        self.model = model
        self._listen = listen
        self.tts = tts()
        self.voice_recognizer = voice_recognizer or VoiceRecognition()
        self.user_name = None
        self.bot_name = bot_name or BOT_NAME
        self.offline_stt = offline_stt
        self.arduino = arduino
        self.vad_iterator = VADIterator(model=model)
        self.audio_queue = queue.Queue(maxsize=150)
        self.utterance_queue = queue.Queue(maxsize=10)
        self.stop_event = threading.Event()
        self.kb_listener = KeyboardListener()
        self.state_lock = threading.Lock()
        self.stream_lock = threading.Lock()

        self.format = pyaudio.paInt16
        self.channels = 1
        self.sample_rate = 16000
        self.chunk = int(self.sample_rate / 10)
        self.num_samples = 512
        self.audio_data = []

        self.vad_last_time = time.time()
        self.vad_reset_threshold = 5

        self.recording_started = False
        self.continue_recording = True
        self.transcription_completed = False
        self.speech_committed = False
        self.text = ""
        self._logger = logger
        self.max_recording_time = 10
        self.is_speaking = False
        self.prev_recognition_time = 0
        self.is_bot = False
        self.listening = False
        self.sleep = False
        self.full_sleep = False

        self.tts_task = None
        self.transcription_task = None
        self.recognition_thread = None
        self.listening_thread = None
        self.capture_thread = None
        self.new_speech = False
        self.stop_vr_flag = False
        self.data = []
        self.interrupt = False
        self.messages = []

        self.py_audio = None
        self.audio_stream = None

        self.start_stream()
        self.save_bot_audio_sample(VOICE_SAMPLE_DIR)
        self.__post_init_threads()

    def __post_init_threads(self):
        self.audio_queue = queue.Queue(maxsize=200)
        self.stop_event = threading.Event()

        self.capture_thread = threading.Thread(target=self.audio_capture, daemon=True)
        self.listening_thread = threading.Thread(target=self.listen, daemon=True)
        # self.recognition_thread = threading.Thread(target=self.run_voice_recognition, daemon=True)
        self.capture_thread.start()
        self.listening_thread.start()
        # self.recognition_thread.start()

    def start_stream(self):
        with self.stream_lock:
            if self.audio_stream is not None and self.audio_stream.is_active():
                return
            self.py_audio = pyaudio.PyAudio()
            self.audio_stream = self.py_audio.open(format=self.format, channels=self.channels, rate=self.sample_rate, input=True, frames_per_buffer=self.chunk)
            logger_.info("Audio streaming started")

    def stop_stream(self):
        with self.stream_lock:
            if not self.audio_stream:
                return

            try:
                if self.audio_stream.is_active():
                    self.audio_stream.stop_stream()
            except Exception as e:
                logger_.error(f"Error stopping audio stream: {e}")

    def close_stream(self):
        with self.stream_lock:
            if self.audio_stream:
                try:
                    if self.audio_stream.is_active():
                        self.audio_stream.stop_stream()
                    self.audio_stream.close()
                except Exception as e:
                    logger_.error(f"Error closing audio stream: {e}")
                finally:
                    self.audio_stream = None

            if self.py_audio:
                try:
                    self.py_audio.terminate()
                except Exception as e:
                    logger_.error(f"Error terminating PyAudio: {e}")
                finally:
                    self.py_audio = None

    def save_bot_audio_sample(self, samples_dir):
        text = f"Hello, my name is {self.bot_name}, your intelligent voice assistant. I'm here to assist you with tasks and answer your queries."
        filename = os.path.join(samples_dir, f"{self.bot_name.lower()}.wav")
        self.tts.save_to_file(text, filename)

    # ─────────────────────────────────────────────────────────────
    # 2. Audio Capture & Processing
    # ─────────────────────────────────────────────────────────────
    def audio_capture(self):
        while not self.stop_event.is_set():
            try:
                with self.stream_lock:
                    if self.audio_stream is None:
                        break
                    frame = self.audio_stream.read(self.num_samples, exception_on_overflow=False)
                self.audio_queue.put(frame, block=False)
            except queue.Full:
                pass
            except Exception as e:
                if not self.stop_event.is_set():
                    logger_.error(f"Error capturing audio: {e}")
                break

    def vad_inference(self, audio_chunk):
        audio_int16 = np.frombuffer(audio_chunk, np.int16)
        audio_float32 = self.int2float(audio_int16)
        with torch.no_grad():
            confidence = self.model(torch.from_numpy(audio_float32), self.sample_rate).item()
        if time.time() - self.vad_last_time > self.vad_reset_threshold:
            self.vad_last_time = time.time()
            vad_iterator.reset_states()
        return confidence

    def convert_to_audio(self, audio_chunks):
        audio_int16_list = [np.frombuffer(chunk, np.int16) for chunk in audio_chunks]
        return np.concatenate(audio_int16_list)

    @staticmethod
    def int2float(sound):
        abs_max = np.abs(sound).max()
        sound = sound.astype("float32")
        if abs_max > 0:
            sound *= 1 / 32768
        return sound.squeeze()

    # ─────────────────────────────────────────────────────────────
    # 3. Listening & VAD Logic
    # ─────────────────────────────────────────────────────────────
    def listen(self, allow_interruption=True, speech_commit_threshold=1, interrupt_threshold=0.1, vad_threshold=0.4, loop=False, recognition_freq=0.2):
        self.continue_recording = True
        self.recording_started = False
        speech_detected = False
        self.data = []
        audio_data = []
        t = time.time()
        st = t
        t2 = t

        if not loop:
            self.start_stream()

        while not self.stop_event.is_set():
            if self.full_sleep:
                break
            try:
                audio_chunk = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            self.data.append(audio_chunk)
            self.data = self.data[-100:]
            audio_data.append(audio_chunk)

            if not self.recording_started and len(audio_data) > 40:
                audio_data = self.data[-20:]

            if not self.recording_started:
                st = time.time()

            if self.kb_listener.key_state.get("x"):
                self.tts.stop()

            if len(self.data) > 50:
                confidence = self.vad_inference(audio_chunk)

                if confidence > vad_threshold and time.time() - st < self.max_recording_time:
                    t = time.time()
                    if not speech_detected:
                        t2 = time.time()
                        speech_detected = True
                        self.data = self.data[-10:]
                        logger_.info("speech_detected")
                        audio_data = self.data

                    self.is_speaking = self.tts.is_playing

                    if not self.recording_started and not self.is_speaking:
                        self.recording_started = True
                        st = time.time()
                        t2 = time.time()

                    elif self.is_speaking:
                        if allow_interruption and time.time() - t2 > interrupt_threshold:
                            # self.audio_data = self.convert_to_audio(self.data[-100:])
                            self.interrupt = True

                else:
                    if time.time() - t > speech_commit_threshold and self.recording_started:
                        if len(audio_data) > 30:
                            logger_.info("speech_committed")
                            self.audio_data = self.convert_to_audio(audio_data)
                            self.is_bot_speaking()
                            self._queue_utterance(self.audio_data.copy(), self.user_name)
                        self.recording_started = False
                        speech_detected = False

    def _reset_audio_state(self):
        self.audio_queue = queue.Queue(maxsize=200)
        self.utterance_queue = queue.Queue(maxsize=10)
        self.audio_data = []
        self.data = []
        self.text = ""
        self.user_name = None
        self.recording_started = False
        self.speech_committed = False
        self.new_speech = False
        self.interrupt = False
        self.is_bot = False
        self.vad_last_time = time.time()
        self.vad_iterator = VADIterator(model=self.model)

    def _queue_utterance(self, audio_data, user_name):
        """Keep complete recordings until the command loop can transcribe them."""
        try:
            self.utterance_queue.put_nowait((audio_data, user_name))
        except queue.Full:
            # Keep current speech responsive if the consumer was blocked for a long time.
            with contextlib.suppress(queue.Empty):
                self.utterance_queue.get_nowait()
            try:
                self.utterance_queue.put_nowait((audio_data, user_name))
            except queue.Full:
                logger_.warning("Transcription queue remained full; dropped the newest utterance")
                return
            logger_.warning("Transcription queue was full; dropped the oldest utterance")
        self.speech_committed = True

    def get_committed_utterance(self):
        try:
            utterance = self.utterance_queue.get_nowait()
        except queue.Empty:
            self.speech_committed = False
            return None
        self.speech_committed = not self.utterance_queue.empty()
        return utterance

    def _stop_background_threads(self, stop_keyboard=False):
        self.listening = False
        self.continue_recording = False
        self.stop_event.set()

        for thread in [self.capture_thread, self.recognition_thread, self.listening_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=2)

        # Fall back to a hard stream stop only if a reader thread did not exit cooperatively.
        if any(thread and thread.is_alive() for thread in [self.capture_thread, self.listening_thread]):
            self.stop_stream()
            for thread in [self.capture_thread, self.listening_thread]:
                if thread and thread.is_alive():
                    thread.join(timeout=1)

        self.close_stream()
        self.capture_thread = None
        self.recognition_thread = None
        self.listening_thread = None

        if stop_keyboard:
            self.kb_listener.stop()

    def enter_sleep_mode(self, speech_timeout=10):
        t = time.time()
        while self.tts.is_playing and time.time() - t < speech_timeout:
            time.sleep(1)

        with self.state_lock:
            if self.full_sleep:
                return False

            self.full_sleep = True
            self.sleep = True
            self.tts.stop()
            self.is_speaking = False
            self._stop_background_threads(stop_keyboard=False)
            self._reset_audio_state()
            logger_.info("Voice assistant entered full sleep mode.")
            return True

    def wake_from_sleep(self):
        with self.state_lock:
            if not self.full_sleep:
                return False

            self.full_sleep = False
            self.sleep = False
            self._reset_audio_state()
            self.start_stream()
            self.__post_init_threads()
            logger_.info("Voice assistant woke from full sleep mode.")
            return True

    def consume_wake_event(self):
        return self.kb_listener.consume_wake_event()

    def _listen_loop(self, **kwargs):
        self.listen(loop=True, allow_interruption=True, **kwargs)

    def start_listener(self, **kwargs):
        if not self.listening_thread or not self.listening_thread.is_alive():
            self.listening = True
            self.listening_thread = threading.Thread(target=self._listen_loop, kwargs=kwargs)
            self.listening_thread.start()
            logger_.info("Voice assistant started listening in background thread.")

    def stop_listener(self, stop_keyboard=True):
        self.full_sleep = False
        self.sleep = False
        self._stop_background_threads(stop_keyboard=stop_keyboard)
        logger_.info("Voice assistant stopped listening.")

    # ─────────────────────────────────────────────────────────────
    # 4. Voice Recognition
    # ─────────────────────────────────────────────────────────────
    def run_voice_recognition(self, interval=0.1, threshold=0.3):
        while not self.stop_event.is_set():
            if len(self.data) > 50 and not self.sleep and (self.recording_started or self.is_speaking):
                self.is_bot_speaking(audio_data=self.data[-50:], threshold=threshold)
            else:
                time.sleep(interval)

    def is_bot_speaking(self, audio_data=None, threshold=0.5):
        if audio_data is None:
            audio_data = self.audio_data

        if any(audio_data):
            results = self.voice_recognizer.recognize_voice(data=audio_data, threshold=threshold)

            if name := results["name"]:
                logger_.info(f"Voice recognition results: {results}")
                self.is_bot = results["name"].lower() == self.bot_name.lower() and self.is_speaking
                if "_" in name:
                    name = " ".join(name.split("_")[:-1])
                self.user_name = name if not self.is_bot else ""

                if self.interrupt and not self.is_bot:
                    logger_.info("speech_interrupted, stopping TTS")
                    self.tts.stop()
                    self.interrupt = False

            self.is_speaking = self.tts.is_playing

    def is_user_authorized(self):
        try:
            user = os.getenv("AUTH_USER") or getpass.getuser()
            return self.user_name.lower() == user.lower()
        except Exception as e:
            logger_.warning(f"Authorization check failed: {e}")
            return False

    # ─────────────────────────────────────────────────────────────
    # 5. Transcription & TTS
    # ─────────────────────────────────────────────────────────────
    async def transcribe_audio(self, callback, repeat_speech, offline_stt=False, audio_data=None, user_name=None):
        try:
            audio_data = self.audio_data.copy() if audio_data is None else audio_data
            self.text = await asyncio.wait_for(asyncio.to_thread(self._listen, audio=audio_data, offline_stt=offline_stt), timeout=15)
            if self.text:
                speaker = self.user_name if user_name is None else user_name
                logger_.info(f"User [{speaker}]: {self.text}" if speaker else f"User: {self.text}")
                if len(self.messages) == 0 or self.messages[-1]["role"] != "user":
                    self.messages.append({"role": "user", "content": self.text})
                else:
                    self.messages[-1]["content"] += "\n" + self.text

                if len(self.messages) > 40:
                    self.messages = self.messages[-40:]

                self.new_speech = True
                if repeat_speech:
                    self.say(self.text)
                if callback:
                    callback(self.text)

        except asyncio.CancelledError:
            logger_.info("Transcription task was interrupted and canceled.")
        except TimeoutError:
            logger_.error("Transcription timed out after 15 seconds")
        except Exception as e:
            logger_.error(f"Error occurred while transcribing audio: {e}")

    def say(self, text, rate=190):
        if self.is_speaking:
            self.tts.stop()

        self.is_speaking = True
        logger_.info(f"Assistant [{self.bot_name}] : {text}")
        self.tts.say(text)

        if len(self.messages) == 0 or self.messages[-1]["role"] != "assistant":
            self.messages.append({"role": "assistant", "content": text})
        else:
            self.messages[-1]["content"] += "\n" + text


# Instantiate
recognizer = VoiceRecognition()
assistant = VoiceAssistant(model=model, listen=listen, tts=TTS2, voice_recognizer=recognizer, logger=logger_, offline_stt=False, bot_name=BOT_NAME)
