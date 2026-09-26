import unittest
from unittest.mock import MagicMock, patch

from src.voice_processing.transcriber import transcribe_file


class TranscriberTests(unittest.TestCase):
    def test_transcribe_file_passes_chunking_kwargs(self):
        mock_pipeline = MagicMock(return_value={"text": "hello world"})

        with patch("src.voice_processing.transcriber.get_whisper_pipeline", return_value=mock_pipeline):
            result = transcribe_file("/tmp/example.mp3")

        self.assertTrue(result.ok)
        self.assertEqual(result.text, "hello world")
        mock_pipeline.assert_called_once_with("/tmp/example.mp3", chunk_length_s=30, stride_length_s=5, return_timestamps=True)

    def test_transcribe_file_reports_empty_transcript(self):
        mock_pipeline = MagicMock(return_value={"text": "   "})

        with patch("src.voice_processing.transcriber.get_whisper_pipeline", return_value=mock_pipeline):
            result = transcribe_file("/tmp/silence.mp3")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "empty_transcript")

    def test_transcribe_file_handles_exceptions(self):
        mock_pipeline = MagicMock(side_effect=RuntimeError("ffmpeg not found"))

        with patch("src.voice_processing.transcriber.get_whisper_pipeline", return_value=mock_pipeline):
            result = transcribe_file("/tmp/corrupt.mp3")

        self.assertFalse(result.ok)
        self.assertIn("ffmpeg not found", result.error)


if __name__ == "__main__":
    unittest.main()
