import configparser
import json
import os
import re
import shlex
import subprocess
import time
import webbrowser
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from src.configs import DESKTOP_APP_DIRS, DESKTOP_INDEX_CACHE_FILE, DESKTOP_INDEX_MAX_CANDIDATES, DESKTOP_INDEX_MAX_DEPTH, DESKTOP_INDEX_REFRESH_SECONDS, DESKTOP_INDEX_ROOTS, OS_TYPE
from src.utilz.logger import logger_
from src.utilz.switch_app import list_open_applications, switch_to_application
from src.utilz.ui_chooser import ChooserItem, show_chooser
from src.utilz.web_search import resolve_website_url

PROJECT_MARKERS = {".git", ".idea", "pyproject.toml", "package.json", "requirements.txt", "Cargo.toml", "go.mod"}
SKIP_DIRS = {".cache", ".git", ".idea", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
SEARCH_PROVIDER_URLS = {
    "google": "https://www.google.com/search?q={query}",
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "github": "https://github.com/search?q={query}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={query}",
    "maps": "https://www.google.com/maps/search/{query}",
}
APP_ALIASES = {
    "browser": ["google chrome", "chrome", "firefox", "brave"],
    "chrome": ["google chrome", "chrome"],
    "files": ["files", "file manager", "nautilus"],
    "explorer": ["file manager", "nautilus", "files"],
    "terminal": ["terminal", "gnome terminal", "konsole", "xterm"],
    "pycharm": ["pycharm", "jetbrains pycharm"],
    "vs code": ["visual studio code", "code"],
}


@dataclass
class ResourceEntry:
    name: str
    path: str
    entry_type: str
    source_root: str
    aliases: list[str] = field(default_factory=list)
    score_boost: int = 0


@dataclass
class AppEntry:
    name: str
    exec_command: list[str]
    desktop_file: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class Resolution:
    ok: bool
    message: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)


class DesktopResolver:
    def __init__(self):
        self.index_roots = [Path(root).expanduser() for root in DESKTOP_INDEX_ROOTS]
        self.app_dirs = [Path(directory).expanduser() for directory in DESKTOP_APP_DIRS]
        self.resource_index: list[ResourceEntry] = []
        self.app_index: list[AppEntry] = []
        self.index_timestamp = 0.0

    @staticmethod
    def normalize_text(text: str) -> str:
        text = text.lower().strip()
        text = text.replace("directory", "folder")
        text = re.sub(r"[^a-z0-9./\-\s]", " ", text)
        text = re.sub(r"\b(?:please|for me|could you|would you|the|a|my)\b", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def search_web(self, query: str, provider: str) -> Resolution:
        provider = provider.lower().strip()
        if provider not in SEARCH_PROVIDER_URLS:
            return Resolution(ok=False, message=f"Search provider {provider} is not supported.", action="search_web")

        query = query.strip()
        url = SEARCH_PROVIDER_URLS[provider].format(query=quote_plus(query))
        webbrowser.open(url)
        return Resolution(ok=True, message=f"Searching for {query} on {provider}.", action="search_web", payload={"provider": provider, "query": query, "url": url})

    def open_website(self, reference: str) -> Resolution:
        url, website = resolve_website_url(reference)
        if not url:
            return Resolution(ok=False, message=f"I could not determine a website from {reference}.", action="open_website")
        webbrowser.open(url)
        return Resolution(ok=True, message=f"Opening {website}.", action="open_website", payload={"url": url, "website": website})

    def refresh_indexes(self, scope: str = "all", force: bool = True) -> Resolution:
        scope = scope.lower().strip()
        if scope not in {"apps", "projects", "directories", "all"}:
            return Resolution(ok=False, message=f"Unknown refresh scope {scope}.", action="refresh_desktop_indexes")

        if scope in {"projects", "directories", "all"}:
            self._ensure_resource_index(force=force)
        if scope in {"apps", "all"}:
            self._ensure_app_index(force=force)

        return Resolution(
            ok=True,
            message=f"Refreshed desktop indexes for {scope}.",
            action="refresh_desktop_indexes",
            payload={"scope": scope, "resources": len(self.resource_index), "apps": len(self.app_index)},
        )

    def list_active_apps(self) -> dict[str, Any]:
        apps = self._list_active_window_entries()
        names = ", ".join(app["name"] for app in apps[:DESKTOP_INDEX_MAX_CANDIDATES]) if apps else "none"
        return {"message": f"Active applications: {names}.", "apps": apps}

    def focus_app(self, name: str) -> Resolution:
        active_apps = self._list_active_window_entries()
        matches = self._rank_active_apps(name, active_apps)
        if not matches:
            return Resolution(ok=False, message=f"I could not find an active application named {name}.", action="focus_app")

        best_score, best_match = matches[0]
        if len(matches) > 1 and best_score < 94 and matches[1][0] >= best_score - 5:
            options = ", ".join(match["name"] for _score, match in matches[:DESKTOP_INDEX_MAX_CANDIDATES])
            return Resolution(ok=False, message=f"Multiple active applications matched {name}: {options}.", action="focus_app_ambiguous")

        switch_to_application(best_match["id"])
        return Resolution(ok=True, message=f"Focusing {best_match['name']}.", action="focus_app", payload=best_match)

    def open_app(self, name: str) -> Resolution:
        self._ensure_app_index()
        matches = self._rank_apps(name)
        if not matches:
            return Resolution(ok=False, message=f"I could not find an application named {name}.", action="open_app")

        best_score, best_app = matches[0]
        if len(matches) > 1 and best_score < 92 and matches[1][0] >= best_score - 6:
            options = ", ".join(app.name for _score, app in matches[:DESKTOP_INDEX_MAX_CANDIDATES])
            return Resolution(ok=False, message=f"Multiple applications matched {name}: {options}.", action="open_app_ambiguous")

        if self._focus_existing_window(best_app):
            return Resolution(ok=True, message=f"Focusing {best_app.name}.", action="focus_app")

        try:
            subprocess.Popen(best_app.exec_command)
        except Exception as exc:
            logger_.error(f"Failed to open app {best_app.name}: {exc}")
            return Resolution(ok=False, message=f"I could not open {best_app.name}.", action="open_app")

        return Resolution(ok=True, message=f"Opening {best_app.name}.", action="open_app", payload=asdict(best_app))

    def open_project(self, name: str) -> Resolution:
        return self._open_indexed_resource(name=name, resource_type="project", use_chooser=True)

    def open_directory(self, name: str) -> Resolution:
        return self._open_indexed_resource(name=name, resource_type="directory", use_chooser=True)

    def _open_indexed_resource(self, name: str, resource_type: str, use_chooser: bool) -> Resolution:
        self._ensure_resource_index()
        matches = self._rank_resources(name=name, resource_type=resource_type)
        if not matches:
            return Resolution(ok=False, message=f"I could not find a {resource_type} named {name}.", action=f"open_{resource_type}")

        best_score, best_entry = matches[0]
        if len(matches) > 1 and best_score < 94 and matches[1][0] >= best_score - 5:
            top_matches = [entry for _score, entry in matches[:DESKTOP_INDEX_MAX_CANDIDATES]]
            if use_chooser:
                shown = self._show_resource_chooser(resource_type=resource_type, entries=top_matches)
                if shown:
                    return Resolution(ok=True, message=f"Multiple {resource_type}s matched {name}. Showing chooser.", action=f"choose_{resource_type}")
            options = ", ".join(entry.name for entry in top_matches)
            return Resolution(ok=False, message=f"Multiple {resource_type}s matched {name}: {options}.", action=f"open_{resource_type}_ambiguous")

        return self._open_path(best_entry.path, best_entry.entry_type, best_entry.name)

    def _rank_resources(self, name: str, resource_type: str) -> list[tuple[int, ResourceEntry]]:
        normalized_name = self.normalize_text(name)
        ranked_entries = []
        for entry in self.resource_index:
            if entry.entry_type != resource_type:
                continue
            score = self.score_candidate(normalized_name, entry.name, entry.aliases) + entry.score_boost
            if normalized_name == self.normalize_text(Path(entry.path).name):
                score += 15
            if score >= 55:
                ranked_entries.append((score, entry))
        ranked_entries.sort(key=lambda item: (item[0], len(item[1].path)), reverse=True)
        return ranked_entries

    def _rank_apps(self, name: str) -> list[tuple[int, AppEntry]]:
        normalized_name = self.normalize_text(name)
        ranked_apps = []
        for app in self.app_index:
            score = self.score_candidate(normalized_name, app.name, app.aliases)
            if score >= 60:
                ranked_apps.append((score, app))
        ranked_apps.sort(key=lambda item: item[0], reverse=True)
        return ranked_apps

    def _rank_active_apps(self, name: str, active_apps: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
        normalized_name = self.normalize_text(name)
        ranked = []
        for app in active_apps:
            aliases = [app.get("wm_class", ""), app.get("title", "")]
            score = self.score_candidate(normalized_name, app["name"], aliases)
            if score >= 55:
                ranked.append((score, app))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked

    def _open_path(self, path: str, entry_type: str, name: str | None = None) -> Resolution:
        try:
            open_command = ["xdg-open", path]
            if entry_type == "project":
                project_command = self._find_project_open_command(path)
                if project_command:
                    open_command = project_command
            subprocess.Popen(open_command)
        except Exception as exc:
            logger_.error(f"Failed to open path {path}: {exc}")
            return Resolution(ok=False, message=f"I could not open {name or path}.", action="open_path")

        title = name or Path(path).name or path
        return Resolution(ok=True, message=f"Opening {title}.", action="open_path", payload={"path": path, "entry_type": entry_type, "name": title})

    def _find_project_open_command(self, path: str) -> list[str] | None:
        self._ensure_app_index()
        preferred_tokens = ("pycharm", "visual studio code", "code")
        for app in self.app_index:
            normalized_name = self.normalize_text(app.name)
            if any(token in normalized_name for token in preferred_tokens):
                return [*app.exec_command, path]
        return None

    def _focus_existing_window(self, app: AppEntry) -> bool:
        if OS_TYPE != "linux":
            return False

        active_apps = self._list_active_window_entries()
        search_terms = [self.normalize_text(app.name), *[self.normalize_text(alias) for alias in app.aliases]]
        for window in active_apps:
            haystack = " ".join([window.get("name", ""), window.get("wm_class", ""), window.get("title", "")])
            lowered = self.normalize_text(haystack)
            if any(term and term in lowered for term in search_terms):
                switch_to_application(window["id"])
                return True
        return False

    def _list_active_window_entries(self) -> list[dict[str, Any]]:
        windows = []
        for raw in list_open_applications():
            if not raw:
                continue
            parts = raw.split(None, 4)
            if len(parts) < 5:
                continue
            window_id, desktop_id, _host, wm_class, title = parts
            name = title.split(" - ")[-1].strip() if title else wm_class.split(".")[-1]
            windows.append({"id": window_id, "desktop": desktop_id, "wm_class": wm_class, "title": title, "name": name})
        return windows

    def _show_resource_chooser(self, resource_type: str, entries: list[ResourceEntry], timeout: int = 10) -> bool:
        items = [ChooserItem(label=f"{entry.name}  [{entry.path}]", value=entry) for entry in entries]

        def on_select(entry: ResourceEntry):
            self._open_path(entry.path, entry.entry_type, entry.name)

        return show_chooser(
            title=f"Select a {resource_type}",
            prompt=f"Select a {resource_type} to open:",
            items=items,
            on_select=on_select,
            timeout=timeout,
        )

    def _ensure_resource_index(self, force: bool = False):
        if self.resource_index and not force and time.time() - self.index_timestamp < DESKTOP_INDEX_REFRESH_SECONDS:
            return
        if not force and self._load_resource_cache():
            return
        self.resource_index = self._scan_resources()
        self.index_timestamp = time.time()
        self._write_resource_cache()

    def _ensure_app_index(self, force: bool = False):
        if self.app_index and not force:
            return
        self.app_index = self._scan_applications()

    def _scan_resources(self) -> list[ResourceEntry]:
        entries: dict[tuple[str, str], ResourceEntry] = {}
        for root in self.index_roots:
            if not root.exists():
                continue
            root_depth = len(root.parts)
            for current_root, dirs, files in os.walk(root):
                current_path = Path(current_root)
                depth = len(current_path.parts) - root_depth
                original_dirs = dirs[:]
                resource_type = "project" if self._is_project_directory(current_path, original_dirs, files) else "directory"
                dirs[:] = [directory for directory in dirs if directory not in SKIP_DIRS and not directory.startswith(".")]
                if depth > DESKTOP_INDEX_MAX_DEPTH:
                    dirs[:] = []
                    continue
                dir_name = current_path.name or str(current_path)
                entry = ResourceEntry(
                    name=dir_name,
                    path=str(current_path),
                    entry_type=resource_type,
                    source_root=str(root),
                    aliases=self._build_aliases(dir_name, current_path),
                    score_boost=8 if resource_type == "project" else 0,
                )
                entries[(entry.path, entry.entry_type)] = entry
        return list(entries.values())

    def _scan_applications(self) -> list[AppEntry]:
        applications: dict[str, AppEntry] = {}
        for app_dir in self.app_dirs:
            if not app_dir.exists():
                continue
            for desktop_file in app_dir.glob("*.desktop"):
                entry = self._parse_desktop_file(desktop_file)
                if entry:
                    applications[entry.name.lower()] = entry
        return list(applications.values())

    def _parse_desktop_file(self, desktop_file: Path) -> AppEntry | None:
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(desktop_file, encoding="utf-8")
            section = parser["Desktop Entry"]
        except Exception:
            return None

        if section.get("NoDisplay", "").lower() == "true":
            return None
        if section.get("Type", "").lower() != "application":
            return None

        name = section.get("Name", "").strip()
        exec_line = section.get("Exec", "").strip()
        if not name or not exec_line:
            return None

        exec_command = self._sanitize_exec(exec_line)
        if not exec_command:
            return None

        aliases = self._build_app_aliases(name, section.get("GenericName", ""))
        return AppEntry(name=name, exec_command=exec_command, desktop_file=str(desktop_file), aliases=aliases)

    @staticmethod
    def _sanitize_exec(exec_line: str) -> list[str]:
        command = re.sub(r"\s+%[fFuUdDnNickvm]", "", exec_line).strip()
        try:
            return shlex.split(command)
        except ValueError:
            return []

    @staticmethod
    def _is_project_directory(current_path: Path, dirs: list[str], files: list[str]) -> bool:
        names = set(dirs) | set(files)
        return any(marker in names for marker in PROJECT_MARKERS)

    def _build_aliases(self, name: str, path: Path) -> list[str]:
        aliases = {name, name.replace("-", " "), name.replace("_", " ")}
        aliases.update(part.replace("-", " ").replace("_", " ") for part in path.parts[-3:])
        return sorted({alias.strip().lower() for alias in aliases if alias.strip()})

    def _build_app_aliases(self, name: str, generic_name: str) -> list[str]:
        aliases = {name, generic_name, self.normalize_text(name)}
        normalized_name = self.normalize_text(name)
        for alias_key, values in APP_ALIASES.items():
            if alias_key == normalized_name or any(value in normalized_name for value in values):
                aliases.update(values)
                aliases.add(alias_key)
        return sorted({alias.strip().lower() for alias in aliases if alias.strip()})

    @staticmethod
    def score_candidate(query: str, name: str, aliases: list[str] | None = None) -> int:
        normalized_query = DesktopResolver.normalize_text(query)
        normalized_name = DesktopResolver.normalize_text(name)
        if not normalized_query or not normalized_name:
            return 0

        candidates = [normalized_name, *(DesktopResolver.normalize_text(alias) for alias in aliases or [])]
        best = 0
        query_tokens = set(normalized_query.split())
        for candidate in candidates:
            if not candidate:
                continue
            score = int(SequenceMatcher(None, normalized_query, candidate).ratio() * 100)
            if candidate == normalized_query:
                score = max(score, 100)
            elif candidate.startswith(normalized_query) or normalized_query.startswith(candidate):
                score = max(score, 92)
            elif normalized_query in candidate or candidate in normalized_query:
                score = max(score, 88)

            candidate_tokens = set(candidate.split())
            if query_tokens and candidate_tokens:
                overlap = len(query_tokens & candidate_tokens) / len(query_tokens | candidate_tokens)
                score = max(score, int(overlap * 100))
                if query_tokens <= candidate_tokens:
                    score = max(score, 90)
            best = max(best, score)
        return best

    def _load_resource_cache(self) -> bool:
        cache_path = Path(DESKTOP_INDEX_CACHE_FILE)
        if not cache_path.exists():
            return False
        try:
            with cache_path.open() as file:
                payload = json.load(file)
            timestamp = payload.get("timestamp", 0)
            if time.time() - timestamp > DESKTOP_INDEX_REFRESH_SECONDS:
                return False
            self.resource_index = [ResourceEntry(**item) for item in payload.get("resources", [])]
            self.index_timestamp = timestamp
            return bool(self.resource_index)
        except Exception as exc:
            logger_.warning(f"Failed to load resource cache: {exc}")
            return False

    def _write_resource_cache(self):
        cache_path = Path(DESKTOP_INDEX_CACHE_FILE)
        payload = {"timestamp": self.index_timestamp, "resources": [asdict(entry) for entry in self.resource_index]}
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with cache_path.open("w") as file:
                json.dump(payload, file)
        except Exception as exc:
            logger_.warning(f"Failed to write resource cache: {exc}")


desktop_resolver = DesktopResolver()
