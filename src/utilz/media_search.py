import os
import re
from dataclasses import dataclass
from pathlib import Path

from src.utilz.desktop_resolver import SKIP_DIRS, DesktopResolver

AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "flac", "ogg", "aac", "opus"}
VIDEO_EXTENSIONS = {"mp4", "mkv", "mov", "avi", "webm"}

LATEST_PATTERN = re.compile(r"\b(latest|newest|most recent|recent|last)\b")
BIGGEST_PATTERN = re.compile(r"\b(biggest|largest)\b")
SMALLEST_PATTERN = re.compile(r"\bsmallest\b")

DIRECTORY_HINTS = {
    "downloads": ("download", "downloaded"),
    "desktop": ("desktop",),
    "documents": ("document",),
    "music": ("music", "song"),
    "videos": ("video",),
}
AUDIO_TYPE_HINTS = ("audio", "recording", "voice note", "voice memo", "sound")
VIDEO_TYPE_HINTS = ("video", "clip", "movie", "recording")

FUZZY_MATCH_FLOOR = 60


@dataclass
class MediaEntry:
    name: str
    path: str
    ext: str
    size_bytes: int
    mtime: float
    source_root: str


def scan_media_files(roots: list[Path], max_depth: int, extensions: set[str]) -> list[MediaEntry]:
    entries: list[MediaEntry] = []
    for root in roots:
        if not root.exists():
            continue
        root_depth = len(root.parts)
        for current_root, dirs, files in os.walk(root):
            current_path = Path(current_root)
            depth = len(current_path.parts) - root_depth
            if depth > max_depth:
                dirs[:] = []
                continue
            dirs[:] = [directory for directory in dirs if directory not in SKIP_DIRS and not directory.startswith(".")]
            for filename in files:
                ext = Path(filename).suffix.lower().lstrip(".")
                if ext not in extensions:
                    continue
                file_path = current_path / filename
                try:
                    stat = file_path.stat()
                except OSError:
                    continue
                entries.append(
                    MediaEntry(
                        name=filename,
                        path=str(file_path),
                        ext=ext,
                        size_bytes=stat.st_size,
                        mtime=stat.st_mtime,
                        source_root=str(root),
                    )
                )
    return entries


def _compute_boosts(normalized_query: str, entry: MediaEntry) -> tuple[int, int, int]:
    """Returns (directory_boost, extension_boost, type_boost) for a candidate."""
    directory_boost = 0
    path_parts = {part.lower() for part in Path(entry.path).parts}
    for directory_name, hints in DIRECTORY_HINTS.items():
        if directory_name in path_parts and any(hint in normalized_query for hint in hints):
            directory_boost = 10
            break

    extension_boost = 15 if entry.ext in normalized_query.split() else 0

    type_boost = 0
    if entry.ext in AUDIO_EXTENSIONS and any(hint in normalized_query for hint in AUDIO_TYPE_HINTS):
        type_boost = 10
    if entry.ext in VIDEO_EXTENSIONS and any(hint in normalized_query for hint in VIDEO_TYPE_HINTS):
        type_boost = 10

    return directory_boost, extension_boost, type_boost


def score_media_candidate(query: str, entry: MediaEntry) -> int:
    base = DesktopResolver.score_candidate(query, entry.name)
    normalized_query = DesktopResolver.normalize_text(query)
    directory_boost, extension_boost, type_boost = _compute_boosts(normalized_query, entry)
    return min(base + directory_boost + extension_boost + type_boost, 100)


def _filter_score(query: str, entry: MediaEntry) -> int:
    """Score used only to decide whether fuzzy filename matches should narrow the candidate pool.

    Deliberately excludes the extension-literal boost: an audio/video file can have any extension, and
    a mentioned extension is often a guess (by the user, or an upstream LLM paraphrasing the request)
    rather than proof this is the intended file. It must never be able to exclude the real target file
    from a "latest"/"biggest" search just because some unrelated file happens to match that extension.
    """
    base = DesktopResolver.score_candidate(query, entry.name)
    normalized_query = DesktopResolver.normalize_text(query)
    directory_boost, _extension_boost, type_boost = _compute_boosts(normalized_query, entry)
    return min(base + directory_boost + type_boost, 100)


def _rank_by_metric(entries: list[MediaEntry], metric_fn, reverse: bool) -> list[tuple[int, MediaEntry]]:
    if not entries:
        return []
    sorted_entries = sorted(entries, key=metric_fn, reverse=reverse)
    best_value = metric_fn(sorted_entries[0])
    worst_value = metric_fn(sorted_entries[-1])
    spread = abs(best_value - worst_value) or 1.0
    scored = []
    for entry in sorted_entries:
        value = metric_fn(entry)
        normalized = 100 * (1 - abs(best_value - value) / spread)
        scored.append((int(normalized), entry))
    return scored


def rank_media_files(query: str, entries: list[MediaEntry]) -> list[tuple[int, MediaEntry]]:
    normalized_query = DesktopResolver.normalize_text(query)
    if not entries:
        return []

    filter_scored = [(_filter_score(query, entry), entry) for entry in entries]
    has_filename_signal = any(score >= FUZZY_MATCH_FLOOR for score, _ in filter_scored)
    candidate_pool = [entry for score, entry in filter_scored if score >= FUZZY_MATCH_FLOOR] if has_filename_signal else entries

    if LATEST_PATTERN.search(normalized_query):
        return _rank_by_metric(candidate_pool, lambda e: e.mtime, reverse=True)
    if BIGGEST_PATTERN.search(normalized_query):
        return _rank_by_metric(candidate_pool, lambda e: e.size_bytes, reverse=True)
    if SMALLEST_PATTERN.search(normalized_query):
        return _rank_by_metric(candidate_pool, lambda e: e.size_bytes, reverse=False)

    scored = [(score_media_candidate(query, entry), entry) for entry in candidate_pool]
    scored.sort(key=lambda item: (item[0], item[1].mtime), reverse=True)
    return scored
