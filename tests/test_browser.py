import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from monitor.services import browser


class BrowserLifecycleTests(SimpleTestCase):
    def test_stale_browser_profile_lock_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            os.symlink("old-container-22", profile / "SingletonLock")
            os.symlink("cookie", profile / "SingletonCookie")
            os.symlink("/tmp/missing-socket", profile / "SingletonSocket")
            self.assertTrue(os.path.lexists(profile / "SingletonLock"))

            browser._clear_stale_profile_lock(directory)

            self.assertFalse(os.path.lexists(profile / "SingletonLock"))
            self.assertFalse(os.path.lexists(profile / "SingletonCookie"))
            self.assertFalse(os.path.lexists(profile / "SingletonSocket"))

    @patch("monitor.services.browser._start_playwright")
    def test_failed_browser_launch_stops_playwright(self, start_playwright):
        playwright = MagicMock()
        start_playwright.return_value = playwright
        playwright.chromium.launch_persistent_context.side_effect = RuntimeError("profile locked")
        browser._context = None
        browser._playwright = None

        with self.assertRaisesRegex(RuntimeError, "profile locked"):
            browser._get_context()

        playwright.stop.assert_called_once_with()
        self.assertIsNone(browser._context)
        self.assertIsNone(browser._playwright)
