import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.utilz.media_search import MediaEntry
from src.utilz.transcription_service import transcription_service
from src.voice_processing.transcriber import TranscriptionResult


class TranscriptionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_transcribe_direct_path_happy_path(self):
        file_path = self.root / "meeting.mp3"
        file_path.write_bytes(b"fake audio data")

        with patch("src.utilz.transcription_service.transcribe_file", return_value=TranscriptionResult(ok=True, text="hello world", elapsed_seconds=1.2)):
            outcome = transcription_service.transcribe(str(file_path))

        self.assertTrue(outcome.ok)
        transcript_path = file_path.with_name("meeting_transcript.txt")
        self.assertTrue(transcript_path.exists())
        self.assertEqual(transcript_path.read_text(encoding="utf-8"), "hello world")
        self.assertIn("Transcribed meeting.mp3", outcome.message)

    def test_ambiguous_match_shows_chooser(self):
        entry_a = MediaEntry(name="a.mp3", path=str(self.root / "a.mp3"), ext="mp3", size_bytes=10, mtime=1.0, source_root=str(self.root))
        entry_b = MediaEntry(name="b.mp3", path=str(self.root / "b.mp3"), ext="mp3", size_bytes=10, mtime=1.0, source_root=str(self.root))
        ranked = [(90, entry_a), (89, entry_b)]

        with (
            patch("src.utilz.transcription_service.scan_media_files", return_value=[entry_a, entry_b]),
            patch("src.utilz.transcription_service.rank_media_files", return_value=ranked),
            patch("src.utilz.transcription_service.show_chooser", return_value=True) as chooser,
        ):
            outcome = transcription_service.transcribe("ambiguous query")

        self.assertTrue(outcome.ok)
        self.assertIn("Showing chooser", outcome.message)
        chooser.assert_called_once()

    def test_open_folder_calls_xdg_open(self):
        file_path = self.root / "clip.mp4"
        file_path.write_bytes(b"data")

        with (
            patch("src.utilz.transcription_service.transcribe_file", return_value=TranscriptionResult(ok=True, text="text", elapsed_seconds=0.5)),
            patch("src.utilz.transcription_service.subprocess.Popen") as popen,
        ):
            outcome = transcription_service.transcribe(str(file_path), open_folder=True)

        self.assertTrue(outcome.ok)
        popen.assert_called_once_with(["xdg-open", str(file_path.parent)])

    def test_picker_mode_selects_file_and_transcribes(self):
        file_path = self.root / "picked.mp3"
        file_path.write_bytes(b"data")

        with (
            patch("src.utilz.transcription_service.TRANSCRIBE_FILE_SELECTION", "picker"),
            patch("src.utilz.transcription_service.pick_file", return_value=str(file_path)) as picker,
            patch("src.utilz.transcription_service.transcribe_file", return_value=TranscriptionResult(ok=True, text="picked text", elapsed_seconds=0.4)),
        ):
            outcome = transcription_service.transcribe("some description that is ignored")

        picker.assert_called_once()
        self.assertTrue(outcome.ok)
        transcript_path = file_path.with_name("picked_transcript.txt")
        self.assertEqual(transcript_path.read_text(encoding="utf-8"), "picked text")

    def test_picker_mode_cancelled_reports_no_file_selected(self):
        with (
            patch("src.utilz.transcription_service.TRANSCRIBE_FILE_SELECTION", "picker"),
            patch("src.utilz.transcription_service.pick_file", return_value=None),
        ):
            outcome = transcription_service.transcribe("some description")

        self.assertFalse(outcome.ok)
        self.assertIn("No file was selected", outcome.message)

    def test_no_match_found(self):
        with patch("src.utilz.transcription_service.MEDIA_SEARCH_ROOTS", [str(self.root)]):
            outcome = transcription_service.transcribe("nonexistent xyz")

        self.assertFalse(outcome.ok)
        self.assertIn("could not find", outcome.message)

    def test_empty_transcript_reported(self):
        file_path = self.root / "silence.mp3"
        file_path.write_bytes(b"data")

        with patch(
            "src.utilz.transcription_service.transcribe_file",
            return_value=TranscriptionResult(ok=False, text="", elapsed_seconds=0.1, error="empty_transcript"),
        ):
            outcome = transcription_service.transcribe(str(file_path))

        self.assertFalse(outcome.ok)
        self.assertIn("did not contain any recognizable speech", outcome.message)

    def test_transcription_failure_reported(self):
        file_path = self.root / "corrupt.mp3"
        file_path.write_bytes(b"data")

        with patch(
            "src.utilz.transcription_service.transcribe_file",
            return_value=TranscriptionResult(ok=False, text="", elapsed_seconds=0.1, error="boom"),
        ):
            outcome = transcription_service.transcribe(str(file_path))

        self.assertFalse(outcome.ok)
        self.assertIn("could not transcribe", outcome.message)

    def test_run_reports_missing_file(self):
        entry = MediaEntry(name="ghost.mp3", path=str(self.root / "ghost.mp3"), ext="mp3", size_bytes=10, mtime=1.0, source_root=str(self.root))

        outcome = transcription_service._run(entry, open_folder=False)

        self.assertFalse(outcome.ok)
        self.assertIn("no longer exists", outcome.message)

    def test_run_reports_empty_file(self):
        file_path = self.root / "empty.mp3"
        file_path.write_bytes(b"")
        entry = MediaEntry(name="empty.mp3", path=str(file_path), ext="mp3", size_bytes=0, mtime=1.0, source_root=str(self.root))

        outcome = transcription_service._run(entry, open_folder=False)

        self.assertFalse(outcome.ok)
        self.assertIn("empty", outcome.message)


if __name__ == "__main__":
    unittest.main()
