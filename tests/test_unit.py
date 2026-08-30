"""Unit tests for shield-bypass engine and plugins (standard unittest)."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from bypass.browser import extension_dir, find_chrome, launch_kwargs
from bypass.config import default_port, ensure_display, session_dir
from bypass.fingerprint import format_curl_cmd, format_python_code
from bypass.plugins.base import BaseChallengePlugin, DetectionResult, SolveResult
from bypass.plugins import PluginRegistry, detect_challenge
from bypass.plugins.cf_turnstile import (
    CfTurnstilePlugin,
    _is_widget_iframe_box,
    click_turnstile_checkbox,
)
from bypass.plugins.cf_waf import CfWafPlugin
from bypass.plugins.recaptcha import RecaptchaPlugin
from bypass.plugins.hcaptcha import HcaptchaPlugin
from bypass.plugins.generic_wait import GenericWaitPlugin
from bypass.session import cdp_url, read_meta, write_meta


class TestShieldBypass(unittest.TestCase):
    def test_extension_files(self):
        ext = extension_dir()
        self.assertTrue((ext / "manifest.json").is_file())
        js = (ext / "script.js").read_text(encoding="utf-8")
        self.assertIn("PointerEvent", js)
        self.assertIn("screenX", js)
        self.assertIn("__cfTurnstileClickPatch", js)
        monitor = (ext / "monitor.js").read_text(encoding="utf-8")
        self.assertIn("data-cf-ts-state", monitor)
        manifest = (ext / "manifest.json").read_text(encoding="utf-8")
        self.assertIn("monitor.js", manifest)
        self.assertIn("match_origin_as_fallback", manifest)

    def test_iframe_bounding_boxes(self):
        self.assertFalse(_is_widget_iframe_box({"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}))
        self.assertFalse(_is_widget_iframe_box({"x": 1200.0, "y": 12.0, "width": 24.0, "height": 24.0}))
        self.assertTrue(_is_widget_iframe_box({"x": 48.0, "y": 250.0, "width": 300.0, "height": 65.0}))

    def test_launch_kwargs(self):
        kw = launch_kwargs()
        self.assertTrue(kw["no_viewport"])
        self.assertIn("--disable-extensions", kw["ignore_default_args"])
        joined = " ".join(kw["args"])
        self.assertIn("--load-extension=", joined)
        self.assertIn("--ozone-platform=x11", joined)
        self.assertIn("ExtensionsMenuAccessControl", joined)
        self.assertIn("--no-sandbox", joined)
        chrome = find_chrome()
        if chrome:
            self.assertEqual(kw.get("executable_path"), chrome)
            self.assertNotIn("channel", kw)
        else:
            self.assertEqual(kw.get("channel"), "chrome")

    def test_display_and_cdp_config(self):
        env = ensure_display({"DISPLAY": ":1", "HOME": "/tmp"})
        self.assertEqual(env["DISPLAY"], ":1")
        self.assertEqual(cdp_url(9333), "http://127.0.0.1:9333")
        self.assertEqual(default_port(), 9333)

    def test_plugin_registry(self):
        reg = PluginRegistry()
        plugins = reg.list_plugins()
        self.assertGreaterEqual(len(plugins), 5)
        names = [p["name"] for p in plugins]
        self.assertIn("cf_waf", names)
        self.assertIn("cf_turnstile", names)
        self.assertIn("recaptcha", names)
        self.assertIn("hcaptcha", names)
        self.assertIn("generic_wait", names)

        # Priority ordering
        priorities = [p["priority"] for p in plugins]
        self.assertEqual(priorities, sorted(priorities))

    def test_fingerprint_formatters(self):
        fp = {
            "url": "https://example.com",
            "fingerprint": {
                "navigator": {
                    "userAgent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                    "language": "en-US",
                },
            },
            "cookies": [
                {"name": "cf_clearance", "value": "test_token_123", "domain": "example.com"},
                {"name": "session_id", "value": "abc987", "domain": "example.com"},
            ],
            "cookie_header": "cf_clearance=test_token_123; session_id=abc987",
            "headers": {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Accept-Language": "en-US",
                "Cookie": "cf_clearance=test_token_123; session_id=abc987",
            },
        }

        curl_cmd = format_curl_cmd("https://example.com", fp)
        self.assertIn("curl -sSL", curl_cmd)
        self.assertIn("'https://example.com'", curl_cmd)
        self.assertIn("cf_clearance=test_token_123", curl_cmd)
        self.assertIn("-H 'User-Agent:", curl_cmd)

        py_code = format_python_code("https://example.com", fp)
        self.assertIn("from curl_cffi import requests", py_code)
        self.assertIn('"Cookie": "cf_clearance=test_token_123; session_id=abc987"', py_code)
        self.assertIn("requests.get(", py_code)

    def test_session_meta_io(self):
        with tempfile.TemporaryDirectory() as td:
            old = os.environ.get("SHIELD_BYPASS_SESSION_DIR")
            try:
                os.environ["SHIELD_BYPASS_SESSION_DIR"] = td
                data = {"cdp_url": "http://127.0.0.1:9333", "pid": 12345}
                write_meta(data)
                loaded = read_meta()
                self.assertEqual(loaded, data)
            finally:
                if old is not None:
                    os.environ["SHIELD_BYPASS_SESSION_DIR"] = old
                else:
                    os.environ.pop("SHIELD_BYPASS_SESSION_DIR", None)


if __name__ == "__main__":
    unittest.main()
