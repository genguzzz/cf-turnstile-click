"""Launch Patchright Chromium with anti-detection and extension patches loaded."""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from bypass.config import (
    debug_log,
    default_profile,
    ensure_display,
    is_headless,
)
from bypass.errors import BypassError


def extension_dir() -> Path:
    """Return the absolute path to the bundled patch extension."""
    return Path(__file__).resolve().parent / "ext"


def find_chrome() -> str | None:
    """Resolve Chrome / Chromium binary across various environments."""
    for key in ("SHIELD_BYPASS_CHROME", "CF_TURNSTILE_CHROME", "CHROME_PATH", "AGENT_BROWSER_EXECUTABLE_PATH"):
        raw = os.environ.get(key, "").strip()
        if raw and Path(raw).is_file():
            return raw

    # Search Playwright cache (highest build number wins)
    base = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / ".cache" / "ms-playwright")
    if base.is_dir():
        candidates: list[tuple[int, Path]] = []
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
                        digits = "".join(c for c in entry.name if c.isdigit())
                        build = int(digits) if digits else 0
                    except ValueError:
                        build = 0
                    candidates.append((build, p))
        if candidates:
            candidates.sort(key=lambda t: t[0], reverse=True)
            return str(candidates[0][1])

    # System binaries
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
    """Return Chrome CLI arguments to load the patch extension and disable detection."""
    ext = str(extension_dir())
    args = [
        f"--disable-extensions-except={ext}",
        f"--load-extension={ext}",
        "--enable-extensions",
        "--ozone-platform=x11",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--enable-unsafe-extension-debugging",
        "--disable-features=DisableLoadExtensionCommandLineSwitch,ExtensionsMenuAccessControl",
    ]
    return args


def launch_kwargs(*, headless: bool | None = None, extra_args: list[str] | None = None) -> dict:
    """Generate launch kwargs for patchright launch_persistent_context."""
    if headless is None:
        headless = is_headless()

    args = launch_extension_args()
    if extra_args:
        args.extend(extra_args)

    kwargs: dict = {
        "headless": headless,
        "no_viewport": True,
        "ignore_default_args": ["--enable-automation", "--disable-extensions"],
        "args": args,
    }
    chrome = find_chrome()
    if chrome:
        kwargs["executable_path"] = chrome
    else:
        kwargs["channel"] = "chrome"
    return kwargs


@contextmanager
def chrome_context(
    *,
    headless: bool | None = None,
    profile_dir: str | None = None,
    cdp: str | None = None,
):
    """Context manager yielding (page, context).

    If `cdp` or `SHIELD_BYPASS_CDP` / `CF_TURNSTILE_CDP` is set, attaches to existing session.
    Otherwise launches a fresh Patchright persistent context.
    """
    try:
        from patchright.sync_api import sync_playwright
    except ImportError as e:
        raise BypassError("patchright is required: pip install patchright") from e

    endpoint = (cdp or os.environ.get("SHIELD_BYPASS_CDP") or os.environ.get("CF_TURNSTILE_CDP") or "").strip()
    if endpoint:
        from bypass.session import attach_cdp

        with attach_cdp(endpoint) as (page, context):
            yield page, context
        return

    # Ensure display is ready for headed/headless Linux
    ensure_display()

    owned = profile_dir is None
    profile = profile_dir or tempfile.mkdtemp(prefix="shield-bypass-")
    debug_log(f"Launching persistent Chrome context with profile={profile}")

    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                profile,
                **launch_kwargs(headless=headless),
            )
        except Exception as e:
            raise BypassError(f"Failed to launch Chrome: {e}") from e

        try:
            page = context.pages[0] if context.pages else context.new_page()
            yield page, context
        finally:
            try:
                context.close()
            except Exception:
                pass

    if owned:
        try:
            shutil.rmtree(profile, ignore_errors=True)
        except Exception:
            pass
