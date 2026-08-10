import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import downloader_core
from downloader_core import (
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_SETTINGS,
    add_history_entry,
    available_resolutions,
    build_ydl_options,
    clear_history,
    is_collection,
    load_history,
    load_settings,
    sanitize_filename,
    save_settings,
    split_urls,
    validate_url,
)


class DownloaderCoreTests(unittest.TestCase):
    def test_default_folder_is_relative_to_application(self):
        self.assertEqual(DEFAULT_DOWNLOAD_DIR.parent, Path(__file__).resolve().parents[1])

    def test_validate_url_accepts_http_and_https(self):
        self.assertEqual(validate_url(" https://example.com/watch?v=1 "), "https://example.com/watch?v=1")
        self.assertEqual(validate_url("http://example.com/video"), "http://example.com/video")

    def test_validate_url_rejects_incomplete_or_unsafe_values(self):
        for value in ("", "youtube.com/watch?v=1", "file:///tmp/video", "javascript:alert(1)"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_url(value)

    def test_sanitize_filename_removes_invalid_characters(self):
        self.assertEqual(sanitize_filename(' Canal: "Teste"? '), "Canal_ _Teste__")
        self.assertEqual(sanitize_filename("...", fallback="Coleção"), "Coleção")

    def test_available_resolutions_are_unique_and_sorted(self):
        info = {
            "formats": [
                {"height": 720, "vcodec": "avc1"},
                {"height": 1080, "vcodec": "vp9"},
                {"height": 720, "vcodec": "vp9"},
                {"height": None, "vcodec": "none"},
            ]
        }
        self.assertEqual(
            available_resolutions(info),
            ["1080p", "720p", "Melhor qualidade", "Só o áudio"],
        )

    def test_collection_types(self):
        self.assertTrue(is_collection({"_type": "playlist"}))
        self.assertTrue(is_collection({"_type": "channel"}))
        self.assertFalse(is_collection({"_type": "video"}))

    def test_audio_options_include_conversion(self):
        options = build_ydl_options("Só o áudio", "mp3", "output.%(ext)s")
        self.assertEqual(options["format"], "bestaudio/best")
        self.assertEqual(options["postprocessors"][0]["preferredcodec"], "mp3")

    def test_mp4_options_prefer_compatible_streams_and_limit_height(self):
        options = build_ydl_options("720p", "mp4", "output.%(ext)s")
        self.assertIn("[height<=720]", options["format"])
        self.assertIn("[ext=mp4]", options["format"])
        self.assertEqual(options["merge_output_format"], "mp4")

    def test_invalid_format_is_rejected(self):
        with self.assertRaises(ValueError):
            build_ydl_options("Só o áudio", "exe", "output.%(ext)s")

    def test_split_urls_ignores_blank_lines_and_duplicates(self):
        raw = "https://a.com\n\n  https://b.com  \nhttps://a.com\n"
        self.assertEqual(split_urls(raw), ["https://a.com", "https://b.com"])


class SettingsAndHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        tmp_path = Path(self.tmp_dir.name)
        patcher_settings = patch.object(downloader_core, "SETTINGS_FILE", tmp_path / "settings.json")
        patcher_history = patch.object(downloader_core, "HISTORY_FILE", tmp_path / "history.json")
        self.addCleanup(patcher_settings.stop)
        self.addCleanup(patcher_history.stop)
        patcher_settings.start()
        patcher_history.start()

    def test_load_settings_returns_defaults_when_no_file_exists(self):
        self.assertEqual(load_settings(), DEFAULT_SETTINGS)

    def test_save_settings_persists_only_known_keys(self):
        save_settings(resolution="720p", unknown_key="ignored")
        settings = load_settings()
        self.assertEqual(settings["resolution"], "720p")
        self.assertNotIn("unknown_key", settings)

    def test_history_starts_empty_and_accepts_entries(self):
        self.assertEqual(load_history(), [])
        add_history_entry("Meu vídeo", "https://example.com/v", "C:/downloads")
        entries = load_history()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "Meu vídeo")
        self.assertEqual(entries[0]["destination"], "C:/downloads")

    def test_history_keeps_most_recent_entry_first(self):
        add_history_entry("Primeiro", "https://example.com/1", "C:/downloads")
        add_history_entry("Segundo", "https://example.com/2", "C:/downloads")
        entries = load_history()
        self.assertEqual(entries[0]["title"], "Segundo")
        self.assertEqual(entries[1]["title"], "Primeiro")

    def test_clear_history_removes_all_entries(self):
        add_history_entry("Item", "https://example.com/1", "C:/downloads")
        clear_history()
        self.assertEqual(load_history(), [])


if __name__ == "__main__":
    unittest.main()
