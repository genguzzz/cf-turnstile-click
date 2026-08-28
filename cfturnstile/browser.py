"""Launch Patchright Chrome with the screenX patch extension loaded."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager

from cfturnstile.errors import TurnstileError


def extension_dir() -> Path:
    return Path(__file__).resolve().parent / "ext"


def launch_extension_args() -> list[str]:
    ext = str(extension_dir())
    return [
        "--disable-features=DisableLoadExtensionCommandLineSwitch",
        f"--disable-extensions-except={ext}",
        f"--load-extension={ext}",
    ]


def launch_kwargs(*, headless: bool | str = False) -> dict:
    """kwargs for ``chromium.launch_persistent_context``.

    Patchright rules: real Chrome, no custom UA, ``no_viewport``, no
    ``add_init_script``. We also load ``ext/`` and keep extensions enabled.
    """
    env = os.environ.get("CF_TURNSTILE_HEADLESS", "").strip().lower()
    if env in {"1", "true", "yes"}:
        headless = True
    return {
        "channel": "chrome",
        "headless": headless,
        "no_viewport": True,
        "ignore_default_args": ["--enable-automation", "--disable-extensions"],
        "args": launch_extension_args(),
    }


@contextmanager
def chrome_context(*, headless: bool | str = False, profile_dir: str | None = None):
    """Yield ``(page, context)`` from Patchright + system Chrome.

    Headed is required for OS-level clicks (and more reliable for Turnstile).
    """
    try:
        from patchright.sync_api import sync_playwright
    except ImportError as e:
        raise TurnstileError("pip install 'cfturnstile'  (needs patchright)") from e

    owned = profile_dir is None
    profile = profile_dir or tempfile.mkdtemp(prefix="cf-turnstile-")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            profile,
            **launch_kwargs(headless=headless),
        )
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
