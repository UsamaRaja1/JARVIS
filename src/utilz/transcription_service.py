import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.configs import DESKTOP_INDEX_MAX_CANDIDATES, MEDIA_SEARCH_MAX_DEPTH, MEDIA_SEARCH_ROOTS, TRANSCRIBE_FILE_SELECTION
from src.utilz.logger import logger_
from src.utilz.media_search import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, MediaEntry, rank_media_files, scan_media_files
from src.utilz.ui_chooser import ChooserItem, pick_file, show_chooser
from src.voice_processing.transcriber import transcribe_file

SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


@dataclass
class TranscriptionOutcome:
    ok: bool
    message: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)


class TranscriptionService:
    def transcribe(self, query: str, open_folder: bool = False) -> TranscriptionOutcome:
        expanded_path = os.path.expanduser(query.strip())
        if os.path.isfile(expanded_path):
            try:
                entry = self._entry_from_path(expanded_path)
            except OSError as exc:
                logger_.error(f"Failed to stat {expanded_path}: {exc}")
                return TranscriptionOutcome(ok=False, message=f"I could not access {expanded_path}.", action="transcribe_audio")
            return self._run(entry, open_folder)

        if TRANSCRIBE_FILE_SELECTION == "picker":
            return self._transcribe_via_picker(query, open_folder)

        roots = [Path(root).expanduser() for root in MEDIA_SEARCH_ROOTS]
        entries = scan_media_files(roots, MEDIA_SEARCH_MAX_DEPTH, SUPPORTED_EXTENSIONS)
        matches = rank_media_files(query, entries)
        if not matches:
            return TranscriptionOutcome(ok=False, message=f"I could not find an audio or video file matching '{query}'.", action="transcribe_audio")

        best_score, best_entry = matches[0]
        if len(matches) > 1 and best_score < 94 and matches[1][0] >= best_score - 5:
            top_matches = [entry for _score, entry in matches[:DESKTOP_INDEX_MAX_CANDIDATES]]
            items = [ChooserItem(label=f"{entry.name}  [{entry.path}]", value=entry) for entry in top_matches]

            def on_select(entry: MediaEntry):
                self._run(entry, open_folder)

            shown = show_chooser(
                title="Select a file to transcribe",
                prompt="Select an audio or video file to transcribe:",
                items=items,
                on_select=on_select,
            )
            if shown:
                return TranscriptionOutcome(ok=True, message=f"Multiple files matched '{query}'. Showing chooser.", action="transcribe_audio_ambiguous")
            options = ", ".join(entry.name for entry in top_matches)
            return TranscriptionOutcome(ok=False, message=f"Multiple files matched '{query}': {options}.", action="transcribe_audio_ambiguous")

        return self._run(best_entry, open_folder)

    def _transcribe_via_picker(self, query: str, open_folder: bool) -> TranscriptionOutcome:
        initial_dir = next((root for root in MEDIA_SEARCH_ROOTS if os.path.isdir(os.path.expanduser(root))), os.path.expanduser("~"))
        selected_path = pick_file(
            title=f"Select a file to transcribe (you asked for: '{query}')",
            initial_dir=os.path.expanduser(initial_dir),
            extensions=sorted(SUPPORTED_EXTENSIONS),
        )
        if not selected_path:
            return TranscriptionOutcome(ok=False, message="No file was selected.", action="transcribe_audio")

        try:
            entry = self._entry_from_path(selected_path)
        except OSError as exc:
            logger_.error(f"Failed to stat {selected_path}: {exc}")
            return TranscriptionOutcome(ok=False, message=f"I could not access {selected_path}.", action="transcribe_audio")

        return self._run(entry, open_folder)

    @staticmethod
    def _entry_from_path(path: str) -> MediaEntry:
        file_path = Path(path)
        stat = file_path.stat()
        return MediaEntry(
            name=file_path.name,
            path=str(file_path),
            ext=file_path.suffix.lower().lstrip("."),
            size_bytes=stat.st_size,
            mtime=stat.st_mtime,
            source_root=str(file_path.parent),
        )

    def _run(self, entry: MediaEntry, open_folder: bool) -> TranscriptionOutcome:
        file_path = Path(entry.path)
        if not file_path.exists():
            return TranscriptionOutcome(ok=False, message=f"The file {entry.name} no longer exists.", action="transcribe_audio")
        if file_path.stat().st_size == 0:
            return TranscriptionOutcome(ok=False, message=f"{entry.name} is empty and cannot be transcribed.", action="transcribe_audio")
        if entry.ext not in SUPPORTED_EXTENSIONS:
            return TranscriptionOutcome(ok=False, message=f"{entry.name} is not a supported audio or video format.", action="transcribe_audio")

        result = transcribe_file(entry.path)
        if not result.ok:
            if result.error == "empty_transcript":
                message = f"{entry.name} did not contain any recognizable speech."
            else:
                message = f"I could not transcribe {entry.name} — the file may be corrupted or in an unsupported format."
            return TranscriptionOutcome(ok=False, message=message, action="transcribe_audio")

        transcript_path = file_path.with_name(f"{file_path.stem}_transcript.txt")
        try:
            transcript_path.write_text(result.text, encoding="utf-8")
        except OSError as exc:
            logger_.error(f"Failed to write transcript for {entry.path}: {exc}")
            return TranscriptionOutcome(ok=False, message=f"I transcribed {entry.name} but could not save the transcript: {exc}.", action="transcribe_audio")

        if open_folder:
            try:
                subprocess.Popen(["xdg-open", str(file_path.parent)])
            except Exception as exc:
                logger_.error(f"Failed to open folder {file_path.parent}: {exc}")

        message = f"Transcribed {entry.name} in {result.elapsed_seconds:.1f}s. Saved to {transcript_path.name}."
        return TranscriptionOutcome(
            ok=True,
            message=message,
            action="transcribe_audio",
            payload={"source": entry.path, "transcript_path": str(transcript_path), "elapsed_seconds": result.elapsed_seconds},
        )


transcription_service = TranscriptionService()
