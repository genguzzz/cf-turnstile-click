"""Launch Patchright Chromium with the screenX patch extension loaded."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from cfturnstile.errors import TurnstileError


def extension_dir() -> Path:
    return Path(__file__).resolve().parent / "ext"


def find_chrome() -> str | None:
    """Prefer an explicit binary, then Playwright cache, then system Chromium."""
    for key in ("CF_TURNSTILE_CHROME", "CHROME_PATH"):
        raw = os.environ.get(key, "").strip()
        if raw and Path(raw).is_file():
            return raw
    base = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / ".cache" / "ms-playwright")
    if base.is_dir():
        hits: list[tuple[int, Path]] = []
        for entry in base.iterdir():
            if not entry.name.startswith("chromium"):
                continue
            for rel in (
                "chrome-linux/chrome",
                "chrome-linux64/chrome",
                "chrome-win/chrome.exe",
                "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
            ):
                p = entry.joinpath(*rel.split("/"))
                if p.is_file():
                    try:
                        build = int("".join(c for c in entry.name if c.isdigit()) or "0")
                    except ValueError:
                        build = 0
                    hits.append((build, p))
        if hits:
            hits.sort(key=lambda t: t[0], reverse=True)
            return str(hits[0][1])
    for p in (
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ):
        if Path(p).is_file():
            return p
    return None


def launch_extension_args() -> list[str]:
    ext = str(extension_dir())
    return [
        "--disable-features=DisableLoadExtensionCommandLineSwitch",
        f"--disable-extensions-except={ext}",
        f"--load-extension={ext}",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]


def launch_kwargs(*, headless: bool | str = False) -> dict:
    """kwargs for ``chromium.launch_persistent_context``.

    Patchright rules: no custom UA, ``no_viewport``, no ``add_init_script``.
    On Linux/Android use ``CF_TURNSTILE_CHROME`` / Playwright Chromium instead
    of ``channel=chrome`` (macOS desktop still prefers system Chrome).
    """
    env = os.environ.get("CF_TURNSTILE_HEADLESS", "").strip().lower()
    if env in {"1", "true", "yes"}:
        headless = True
    kwargs: dict = {
        "headless": headless,
        "no_viewport": True,
        "ignore_default_args": ["--enable-automation", "--disable-extensions"],
        "args": launch_extension_args(),
    }
    chrome = find_chrome()
    if chrome:
        kwargs["executable_path"] = chrome
    else:
        kwargs["channel"] = "chrome"
    return kwargs


@contextmanager
def chrome_context(*, headless: bool | str = False, profile_dir: str | None = None):
    """Yield ``(page, context)`` from Patchright + Chrome/Chromium."""
    try:
        from patchright.sync_api import sync_playwright
    except ImportError as e:
        raise TurnstileError("pip install 'cfturnstile'  (needs patchright)") from e

    owned = profile_dir is None
    profile = profile_dir or tempfile.mkdtemp(prefix="cf-turnstile-")
    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                profile,
                **launch_kwargs(headless=headless),
            )
        except Exception as e:
            raise TurnstileError(f"failed to launch Chrome/Chromium: {e}") from e
        try:
            page = context.pages[0] if context.pages else context.new_page()
            yield page, context
        finally:
            context.close()
    if owned:
        try:
            import shutil

            shutil.rmtree(profile, ignore_errors=True)
        except Exception:
            pass
