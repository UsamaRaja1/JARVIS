import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.utilz.desktop_resolver import DesktopResolver, ResourceEntry


class DesktopResolverTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.cache_file = str(self.root / "desktop_index.json")
        self.app_dir = self.root / "applications"
        self.app_dir.mkdir()

    def build_resolver(self) -> DesktopResolver:
        resolver = DesktopResolver()
        resolver.index_roots = [self.root]
        resolver.app_dirs = [self.app_dir]
        return resolver

    def test_open_project_by_fuzzy_name(self):
        project = self.root / "Jarvis Assistant"
        project.mkdir()
        (project / ".git").mkdir()

        resolver = self.build_resolver()

        with patch("src.utilz.desktop_resolver.DESKTOP_INDEX_CACHE_FILE", self.cache_file), patch("src.utilz.desktop_resolver.subprocess.Popen") as popen:
            resolution = resolver.open_project("jarvis assitant")

        self.assertTrue(resolution.ok)
        self.assertIn("Opening Jarvis Assistant", resolution.message)
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0][-1], str(project))

    def test_open_directory_uses_chooser_for_ambiguous_matches(self):
        resolver = self.build_resolver()
        ranked_matches = [
            (90, ResourceEntry(name="Reports", path=str(self.root / "Reports"), entry_type="directory", source_root=str(self.root))),
            (89, ResourceEntry(name="Reports Archive", path=str(self.root / "Reports Archive"), entry_type="directory", source_root=str(self.root))),
        ]

        with (
            patch("src.utilz.desktop_resolver.DESKTOP_INDEX_CACHE_FILE", self.cache_file),
            patch.object(resolver, "_rank_resources", return_value=ranked_matches),
            patch.object(resolver, "_show_resource_chooser", return_value=True) as chooser,
        ):
            resolution = resolver.open_directory("reports")

        self.assertTrue(resolution.ok)
        self.assertIn("Showing chooser", resolution.message)
        chooser.assert_called_once()

    def test_open_app_launches_desktop_entry(self):
        desktop_file = self.app_dir / "google-chrome.desktop"
        desktop_file.write_text(
            "\n".join(
                [
                    "[Desktop Entry]",
                    "Type=Application",
                    "Name=Google Chrome",
                    "Exec=/usr/bin/google-chrome-stable %U",
                ]
            )
        )

        resolver = self.build_resolver()

        with patch("src.utilz.desktop_resolver.subprocess.Popen") as popen, patch.object(resolver, "_focus_existing_window", return_value=False):
            resolution = resolver.open_app("chrome")

        self.assertTrue(resolution.ok)
        self.assertEqual(resolution.message, "Opening Google Chrome.")
        popen.assert_called_once_with(["/usr/bin/google-chrome-stable"])

    def test_search_web_opens_provider_results(self):
        resolver = self.build_resolver()

        with patch("src.utilz.desktop_resolver.webbrowser.open") as browser_open:
            resolution = resolver.search_web("websocket reconnect", "youtube")

        self.assertTrue(resolution.ok)
        self.assertIn("Searching for websocket reconnect on youtube.", resolution.message)
        self.assertIn("youtube", browser_open.call_args.args[0])
        self.assertIn("websocket+reconnect", browser_open.call_args.args[0])

    def test_open_website_normalizes_common_inputs(self):
        resolver = self.build_resolver()

        with patch("src.utilz.desktop_resolver.webbrowser.open") as browser_open:
            resolution_a = resolver.open_website("facebook")
            resolution_b = resolver.open_website("facebook.com")
            resolution_c = resolver.open_website("https://facebook.com")

        self.assertTrue(resolution_a.ok)
        self.assertTrue(resolution_b.ok)
        self.assertTrue(resolution_c.ok)
        self.assertEqual(browser_open.call_args_list[0].args[0], "https://www.facebook.com")
        self.assertEqual(browser_open.call_args_list[1].args[0], "https://www.facebook.com")
        self.assertEqual(browser_open.call_args_list[2].args[0], "https://facebook.com")

    def test_list_active_apps_returns_message_and_apps(self):
        resolver = self.build_resolver()

        with patch("src.utilz.desktop_resolver.list_open_applications", return_value=["0x01 0 host google-chrome.Google-chrome ChatGPT - Google Chrome"]):
            result = resolver.list_active_apps()

        self.assertIn("Active applications:", result["message"])
        self.assertEqual(result["apps"][0]["id"], "0x01")


if __name__ == "__main__":
    unittest.main()
