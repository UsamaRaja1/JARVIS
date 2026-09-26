import os
import platform
import shutil
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent  # Goes up 2 levels


USER_NAME = "Sir"
BOT_NAME = "Jarvis"

OS_TYPE = platform.system().lower()

DATA_DIR = os.path.join(root_dir, "src", "data")
VOICE_SAMPLE_DIR = os.path.join(DATA_DIR, "voice-samples")
VOICE_ENCODING_DIR = os.path.join(DATA_DIR, "voice-encodings")
IMAGE_SAMPLE_DIR = os.path.join(DATA_DIR, "images-samples")
IMAGE_ENCODING_DIR = os.path.join(DATA_DIR, "images-encodings")
LOGS_DIR = os.path.join("src", "logs")
RESPONSES_FILE_PATH = os.path.join(DATA_DIR, "responses.txt")
SHARED_DATA_FILE_PATH = os.path.join(DATA_DIR, "shared_data.json")
TEMP_DIR = os.path.join("src", "temp")
USER_CONFIG_FILE_PATH = os.path.join(DATA_DIR, "users.json")
USER_CONFIG_EXAMPLE_FILE_PATH = os.path.join(DATA_DIR, "users.example.json")
SHARED_DATA_EXAMPLE_FILE_PATH = os.path.join(DATA_DIR, "shared_data.example.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(VOICE_SAMPLE_DIR, exist_ok=True)
os.makedirs(VOICE_ENCODING_DIR, exist_ok=True)
os.makedirs(IMAGE_SAMPLE_DIR, exist_ok=True)
os.makedirs(IMAGE_ENCODING_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)


def initialize_runtime_file(path: str, example_path: str) -> None:
    """Create a private runtime file from its committed example on first run."""
    if not os.path.exists(path) and os.path.exists(example_path):
        shutil.copyfile(example_path, path)


initialize_runtime_file(USER_CONFIG_FILE_PATH, USER_CONFIG_EXAMPLE_FILE_PATH)
initialize_runtime_file(SHARED_DATA_FILE_PATH, SHARED_DATA_EXAMPLE_FILE_PATH)


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def env_csv_paths(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


IDLE_SLEEP_TIMEOUT_SECONDS = env_int("IDLE_SLEEP_TIMEOUT_SECONDS", env_int("DEEP_SLEEP", 300))
FOLLOW_UP_WINDOW_SECONDS = env_int("FOLLOW_UP_WINDOW_SECONDS", env_int("SOFT_SLEEP", 120))

HOME_DIR = str(Path.home())
DESKTOP_INDEX_ROOTS = env_csv_paths(
    "DESKTOP_INDEX_ROOTS",
    [
        os.path.join(HOME_DIR, "Desktop"),
        os.path.join(HOME_DIR, "Documents"),
        os.path.join(HOME_DIR, "Downloads"),
        os.path.join(HOME_DIR, "Projects"),
        os.path.join(HOME_DIR, "PycharmProjects"),
    ],
)
DESKTOP_APP_DIRS = env_csv_paths(
    "DESKTOP_APP_DIRS",
    [
        os.path.join(HOME_DIR, ".local", "share", "applications"),
        "/usr/share/applications",
        "/var/lib/snapd/desktop/applications",
    ],
)
DESKTOP_INDEX_CACHE_FILE = os.path.join(TEMP_DIR, "desktop_index.json")
DESKTOP_INDEX_MAX_DEPTH = env_int("DESKTOP_INDEX_MAX_DEPTH", 5)
DESKTOP_INDEX_REFRESH_SECONDS = env_int("DESKTOP_INDEX_REFRESH_SECONDS", 900)
DESKTOP_CONTEXT_TTL_SECONDS = env_int("DESKTOP_CONTEXT_TTL_SECONDS", 180)
DESKTOP_INDEX_MAX_CANDIDATES = env_int("DESKTOP_INDEX_MAX_CANDIDATES", 5)

MEDIA_SEARCH_ROOTS = env_csv_paths(
    "MEDIA_SEARCH_ROOTS",
    [
        os.path.join(HOME_DIR, "Downloads"),
        os.path.join(HOME_DIR, "Desktop"),
        os.path.join(HOME_DIR, "Documents"),
        os.path.join(HOME_DIR, "Music"),
        os.path.join(HOME_DIR, "Videos"),
    ],
)
MEDIA_SEARCH_MAX_DEPTH = env_int("MEDIA_SEARCH_MAX_DEPTH", 4)

# "auto" resolves the target file via fuzzy natural-language search; "picker" always shows a native
# OS file-open dialog instead, letting the user select the file manually.
TRANSCRIBE_FILE_SELECTION = os.getenv("TRANSCRIBE_FILE_SELECTION", "auto").strip().lower()
