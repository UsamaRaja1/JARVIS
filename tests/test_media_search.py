import os
import tempfile
import time
import unittest
from pathlib import Path

from src.utilz.media_search import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, rank_media_files, scan_media_files


class MediaSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def make_file(self, relative_path: str, size_bytes: int = 10, mtime_offset: float = 0) -> Path:
        file_path = self.root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"0" * size_bytes)
        if mtime_offset:
            now = time.time()
            os.utime(file_path, (now + mtime_offset, now + mtime_offset))
        return file_path

    def scan(self, extensions=None):
        extensions = extensions or (AUDIO_EXTENSIONS | VIDEO_EXTENSIONS)
        return scan_media_files([self.root], max_depth=4, extensions=extensions)

    def test_fuzzy_filename_match_ranks_closest_name_first(self):
        self.make_file("Meeting_Notes.mp3")
        self.make_file("Random_Song.mp3")

        entries = self.scan()
        matches = rank_media_files("meeting", entries)

        self.assertEqual(matches[0][1].name, "Meeting_Notes.mp3")

    def test_latest_query_reranks_by_mtime(self):
        self.make_file("old_recording.mp3", mtime_offset=-1000)
        self.make_file("newer_recording.mp3", mtime_offset=-500)
        self.make_file("brand_new_recording.mp3", mtime_offset=0)

        entries = self.scan()
        matches = rank_media_files("my latest recording", entries)

        self.assertEqual(matches[0][1].name, "brand_new_recording.mp3")

    def test_biggest_query_reranks_by_size(self):
        self.make_file("small_file.mp3", size_bytes=10)
        self.make_file("big_file.mp3", size_bytes=10_000)

        entries = self.scan()
        matches = rank_media_files("the biggest audio file", entries)

        self.assertEqual(matches[0][1].name, "big_file.mp3")

    def test_extension_mention_boosts_matching_extension(self):
        self.make_file("clip.mp3")
        self.make_file("clip.mp4")

        entries = self.scan()
        matches = rank_media_files("the mp4", entries)

        self.assertEqual(matches[0][1].name, "clip.mp4")

    def test_latest_query_not_derailed_by_unrelated_extension_mention(self):
        # Regression: an upstream LLM paraphrase can hallucinate a specific extension (e.g. "mp3")
        # that the user never said. An unrelated older file matching that extension must not be able
        # to exclude the real, newer file (which can be in any format, e.g. .m4a) from consideration.
        self.make_file("Downloads/podcast.mp3", mtime_offset=-1000)
        self.make_file("Downloads/audio_message (1).m4a", mtime_offset=0)

        entries = self.scan()
        matches = rank_media_files("the latest mp3 in downloads", entries)

        self.assertEqual(matches[0][1].name, "audio_message (1).m4a")

    def test_directory_context_boost_favors_downloads(self):
        self.make_file("Downloads/interview.mp3")
        self.make_file("Documents/interview.mp3")

        entries = self.scan()
        matches = rank_media_files("the interview i downloaded", entries)

        self.assertIn("Downloads", matches[0][1].path)


if __name__ == "__main__":
    unittest.main()
