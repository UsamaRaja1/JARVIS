import asyncio
import os
import struct
import subprocess
import threading

import simpleaudio as sa
import speech_recognition as sr
import torch
from pydub import AudioSegment
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

from src.configs import OS_TYPE, TEMP_DIR
from src.utilz.logger import logger_

festival = None
pyttsx3 = None

if OS_TYPE == "linux":
    try:
        import festival
    except ImportError:
        logger_.debug("Optional Festival bindings are not installed; using eSpeak.")
elif OS_TYPE == "windows":
    import pyttsx3


# ================== Whisper Loader ==================


def load_whisper():
    logger_.info("Loading whisper model")
    DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
    TORCH_DTYPE = torch.float16 if torch.cuda.is_available() else torch.float32
    MODEL_ID = "distil-whisper/distil-large-v2"

    model = AutoModelForSpeechSeq2Seq.from_pretrained(MODEL_ID, torch_dtype=TORCH_DTYPE, low_cpu_mem_usage=True, use_safetensors=True).to(DEVICE)

    processor = AutoProcessor.from_pretrained(MODEL_ID)

    return pipeline(
        "automatic-speech-recognition", model=model, tokenizer=processor.tokenizer, feature_extractor=processor.feature_extractor, max_new_tokens=128, torch_dtype=TORCH_DTYPE, device=DEVICE
    )


_whisper_pipeline = None


def get_whisper_pipeline():
    """Lazily load and return the shared Whisper ASR pipeline singleton."""
    global _whisper_pipeline
    if _whisper_pipeline is None:
        _whisper_pipeline = load_whisper()
    return _whisper_pipeline


# ================== Listener ==================


def listen(timeout=5, audio=None, offline_stt=False):
    recognizer = sr.Recognizer()

    if audio is None:
        with sr.Microphone() as source:
            recognizer.pause_threshold = 1
            recognizer.adjust_for_ambient_noise(source)

            logger_.info("Listening...")
            try:
                audio1 = recognizer.listen(source, timeout=timeout)
            except sr.WaitTimeoutError:
                logger_.error("Timeout occurred. No speech detected.")
                return ""
    else:
        sample_rate = 16000
        sample_width = 2
        frame_data = struct.pack("<" + "h" * len(audio), *audio)
        audio1 = sr.AudioData(frame_data, sample_rate, sample_width)

    try:
        logger_.info("Recognizing...")
        return recognizer.recognize_google(audio1).lower()
    except sr.UnknownValueError:
        logger_.info("Sorry, I could not understand what you said.")
        return ""
    except sr.RequestError as e:
        logger_.error(f"Speech API unavailable. Error: {e}")
        if offline_stt:
            logger_.info("Using whisper for transcription...")
            whisper_pipeline = get_whisper_pipeline()
            return whisper_pipeline(audio)["text"].lower()
        return ""


# ================== TTS Classes ==================


class TTS:
    def __init__(self, rate=190):
        self.interrupt = False
        self.filename = os.path.join(TEMP_DIR, "output.wav")
        self.playback = None
        self.is_playing = False
        if OS_TYPE == "windows":
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", rate)

    async def say(self, text, filename=None):
        self.interrupt = False
        filename = filename or self.filename
        self.save_to_file(text, filename)
        await asyncio.to_thread(self.play_audio)

    def save_to_file(self, text, filename):
        if OS_TYPE == "linux":
            subprocess.run(["espeak", "-w", filename, text], check=True)
        elif OS_TYPE == "windows":
            self.engine.save_to_file(text, filename)
            self.engine.runAndWait()

    def play_audio(self):
        """Play audio with support for interruption."""
        try:
            sound = AudioSegment.from_file(self.filename, format="wav")
            self.is_playing = True
            self.playback = sa.play_buffer(sound.raw_data, num_channels=sound.channels, bytes_per_sample=sound.sample_width, sample_rate=sound.frame_rate)
            while self.playback.is_playing():
                if self.interrupt:
                    self.playback.stop()
                    break
            if self.playback.is_playing():
                self.playback.wait_done()
            self.is_playing = False
        except Exception as e:
            logger_.error(f"Error during playback: {e}")

    def stop(self):
        self.interrupt = True
        if self.playback:
            self.playback.stop()
            self.is_playing = False


class TTS2(TTS):
    def say(self, text, filename=None):
        self.interrupt = False
        filename = filename or self.filename
        self.save_to_file(text, filename)
        self.thread = threading.Thread(target=self.play_audio)
        self.thread.start()

    def stop(self):
        self.interrupt = True
        if self.playback:
            self.playback.stop()
            self.is_playing = False
        if hasattr(self, "thread") and self.thread.is_alive():
            self.thread.join(timeout=1)


# ================== Simple Say Shortcut ==================


def say(text, rate=190):
    if OS_TYPE == "linux":
        if festival is not None:
            festival.sayText(text)
        else:
            subprocess.run(["espeak", text], check=True)
    elif OS_TYPE == "windows":
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.say(text)
        engine.runAndWait()
