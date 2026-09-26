import time
from dataclasses import dataclass

from src.utilz.logger import logger_
from src.voice_processing.speech_models import get_whisper_pipeline


@dataclass
class TranscriptionResult:
    ok: bool
    text: str
    elapsed_seconds: float
    error: str | None = None


def transcribe_file(path: str, chunk_length_s: int = 30, stride_length_s: int = 5) -> TranscriptionResult:
    start = time.monotonic()
    try:
        whisper_pipeline = get_whisper_pipeline()
        logger_.info(f"Transcribing file {path}")
        output = whisper_pipeline(path, chunk_length_s=chunk_length_s, stride_length_s=stride_length_s, return_timestamps=True)
        text = output["text"].strip()
        elapsed = time.monotonic() - start
        if not text:
            return TranscriptionResult(ok=False, text="", elapsed_seconds=elapsed, error="empty_transcript")
        return TranscriptionResult(ok=True, text=text, elapsed_seconds=elapsed)
    except Exception as exc:
        elapsed = time.monotonic() - start
        logger_.error(f"Whisper transcription failed for {path}: {exc}")
        return TranscriptionResult(ok=False, text="", elapsed_seconds=elapsed, error=str(exc))
