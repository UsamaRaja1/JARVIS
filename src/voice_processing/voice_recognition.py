import os
import pickle
import wave
from glob import glob
from threading import Lock

import numpy as np
import pyaudio
import torch
from pyannote.audio import Inference, Model
from pydub import AudioSegment
from scipy.spatial.distance import cdist

from src.configs import BOT_NAME, TEMP_DIR, VOICE_ENCODING_DIR, VOICE_SAMPLE_DIR
from src.utilz.logger import logger_


class VoiceRecognition:
    def __init__(self, format=pyaudio.paInt16, channels=1, sample_rate=16000, chunk=None):
        self.model = None
        self.inference = None
        self.load_model("pyannote/embedding")
        self.voice_dir = VOICE_SAMPLE_DIR
        self.encoding_dir = VOICE_ENCODING_DIR
        self.voice_data = self.load_data()
        self.names = self.voice_data["names"]
        self.audio_encodings = self.voice_data["audio_encodings"]

        self.audio = pyaudio.PyAudio()
        self.format = format
        self.channels = channels
        self.sample_size = self.audio.get_sample_size(format)
        self.sample_rate = sample_rate
        self.chunk = chunk or int(sample_rate / 10)
        self.num_samples = 512
        self.recognition_lock = Lock()

    def load_model(self, model_id):
        hf_token_env = "HF_AUTH_TOKEN"
        logger_.info(f"Loading {model_id} model...")
        # try:
        #     self.model = Model.from_pretrained(model_id, local_files_only=True)
        # except Exception:
        hf_token = os.getenv(hf_token_env)
        #     if not hf_token:
        #         raise OSError(f"Hugging Face token not found. Please set `{hf_token_env}` for the first download.")

        # logger.info("Model not found locally. Downloading from Hugging Face Hub...")
        self.model = Model.from_pretrained(model_id, use_auth_token=hf_token)

        self.inference = Inference(self.model, window="whole")

        # except Exception as e:
        #     raise RuntimeError(f"Error loading {model_id} model: {e}")

    def convert_audio(self, input_files, output_format):
        if isinstance(input_files, str):
            input_files = [input_files]

        for input_file in input_files:
            if output_format.lower() not in ["mp3", "wav"]:
                raise ValueError("Output format must be 'mp3' or 'wav'")

            file_name, _ = os.path.splitext(input_file)
            output_file = f"{file_name}.{output_format}"

            if not os.path.exists(output_file):
                try:
                    audio = AudioSegment.from_file(input_file)
                    audio.export(output_file, format=output_format)
                    logger_.info(f"Converted {input_file} -> {output_file}")
                except Exception as e:
                    logger_.error(f"Audio conversion failed: {e}")

    def generate_audio_encodings(self, audio_paths):
        try:
            names = [os.path.basename(path).split(".")[0] for path in audio_paths]
            os.makedirs(self.encoding_dir, exist_ok=True)

            audio_encodings = []
            logger_.info("Generating/Loading audio encodings...")

            for i, path in enumerate(audio_paths):
                file_path = os.path.join(self.encoding_dir, f"{names[i]}.pkl")

                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        encodings = pickle.load(f)
                else:
                    encoded_audio = self.inference(path).reshape(1, -1)
                    with open(file_path, "wb") as f:
                        pickle.dump(encoded_audio, f)
                    encodings = encoded_audio

                audio_encodings.append(encodings)

            return {"encodings": audio_encodings, "names": names}
        except Exception as e:
            logger_.error(f"Encoding Error: {e}")
            return {"error": str(e), "encodings": [], "names": []}

    def load_data(self, directory=None):
        if directory is None:
            directory = self.voice_dir

        pattern = os.path.join(directory, "*")
        input_paths = glob(pattern)
        self.convert_audio(input_paths, "wav")

        audio_paths = glob(f"{pattern}.wav")
        res = self.generate_audio_encodings(audio_paths)

        return {"names": res["names"], "audio_paths": audio_paths, "audio_encodings": res["encodings"]}

    @staticmethod
    def save_to_wav(filename, frames, channels, sampwidth, sample_rate):
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(sample_rate)
            wf.writeframes(b"".join(frames))

    def capture_audio(self, duration=10, chunk_duration=3, sample_rate=44100, channels=1):
        logger_.info(f"Capturing voice for {duration}s...")
        data = self.load_data(self.voice_dir)
        audio_encodings = data["audio_encodings"]

        format = pyaudio.paInt16
        chunk = 1024
        audio = pyaudio.PyAudio()
        stream = audio.open(format=format, channels=channels, rate=sample_rate, input=True, frames_per_buffer=chunk)

        frames = []
        frame_rate = sample_rate / chunk
        chunks_per_segment = int(chunk_duration * frame_rate)
        total_chunks = int(duration * frame_rate)

        if audio_encodings:
            for _ in range(total_chunks):
                data = stream.read(chunk)
                frames.append(data)

                if len(frames) >= chunks_per_segment:
                    print(self.recognize_voice(frames))
                    frames = frames[-chunks_per_segment:]

        stream.stop_stream()
        stream.close()
        audio.terminate()
        logger_.info("Recording completed.")

    def recognize_voice(self, audio_data=None, data=None, threshold=0.4, log=False, tmp_file=None):
        # if not self.recognition_lock.acquire(blocking=False):
        #     return {"name": "", "score": None}  # or "busy"

        temp_wav_file = tmp_file or os.path.join(TEMP_DIR, "temp_realtime_audio.wav")
        if os.path.dirname(temp_wav_file):
            os.makedirs(os.path.dirname(temp_wav_file), exist_ok=True)

        try:
            names = self.names
            audio_encodings = self.audio_encodings

            if audio_data:
                self.save_to_wav(temp_wav_file, audio_data, self.channels, self.sample_size, self.sample_rate)
                embedding = self.inference(temp_wav_file)
            else:
                samples = np.frombuffer(b"".join(data), dtype=np.int16).astype(np.float32) / 32768
                waveform = torch.tensor(samples).unsqueeze(0)
                embedding = self.inference({"waveform": waveform, "sample_rate": self.sample_rate})

            embedding = np.expand_dims(embedding, 0)
            audio_encodings = np.vstack(audio_encodings)
            distances = cdist(audio_encodings, embedding, "cosine").ravel()

            scores = [(names[i], 1 - distances[i]) for i in range(len(names)) if (1 - distances[i]) > threshold]
            if not scores:
                return {"name": "", "score": None}

            scores.sort(key=lambda x: x[1], reverse=True)
            top_matches = scores[:2]

            user_index = next((i for i, (n, _) in enumerate(top_matches) if n.lower() != BOT_NAME.lower()), None)
            if user_index is not None and user_index != 0:
                top_matches[0], top_matches[user_index] = top_matches[user_index], top_matches[0]

            if log:
                for name, score in top_matches:
                    logger_.info(f"Matched: {name} - {score:.3f}")

            return next({"name": name.title(), "score": score} for name, score in top_matches)

        except Exception as e:
            logger_.error(f"Recognition error: {e}")
            return {"name": "", "score": None}
        finally:
            if os.path.exists(temp_wav_file):
                os.remove(temp_wav_file)
            # self.recognition_lock.release()
