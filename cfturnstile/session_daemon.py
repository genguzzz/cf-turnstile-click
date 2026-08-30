"""Keep Patchright Chrome alive with the same launch_kwargs as ns.sh login."""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

from cfturnstile.browser import launch_kwargs
from cfturnstile.session import (
    cdp_url,
    default_port,
    default_profile,
    ensure_display,
    wait_cdp,
    write_meta,
)


def main() -> None:
    os.environ.update(ensure_display(os.environ.copy()))
    port = default_port()
    profile = Path(os.environ.get("CF_TURNSTILE_PROFILE") or default_profile())
    profile.mkdir(parents=True, exist_ok=True)
    kw = launch_kwargs(headless=False)
    args = list(kw.get("args") or [])
    args.extend(
        [
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
        ]
    )
    kw["args"] = args
    from patchright.sync_api import sync_playwright

    stop = False

    def _on_stop(_signum=None, _frame=None) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _on_stop)
    signal.signal(signal.SIGINT, _on_stop)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(str(profile), **kw)
        url = cdp_url(port)
        wait_cdp(url, timeout_s=20)
        write_meta(
            {
                "pid": os.getpid(),
                "port": port,
                "cdp": url,
                "profile": str(profile),
                "mode": "patchright",
            }
        )
        print(f"cf-turnstile session cdp={url}", flush=True)
        try:
            while not stop:
                time.sleep(0.5)
        finally:
            try:
                context.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
