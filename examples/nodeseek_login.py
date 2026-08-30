#!/usr/bin/env python3
"""NodeSeek login example using shield-bypass."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add scripts directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from bypass import chrome_context, solve

NS_SIGNIN = "https://www.nodeseek.com/signIn.html"


def _load_env_file() -> None:
    p = Path.home() / ".nodeseek-client" / "env"
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))


def main() -> None:
    _load_env_file()
    user = os.environ.get("NS_USER") or os.environ.get("NODESEEK_USER") or ""
    password = os.environ.get("NS_PASS") or os.environ.get("NODESEEK_PASSWORD") or ""
    if not user or not password:
        print("Need NS_USER / NS_PASS or ~/.nodeseek-client/env", file=sys.stderr)
        raise SystemExit(2)

    with chrome_context(headless=False) as (page, context):
        page.goto(NS_SIGNIN, wait_until="domcontentloaded")
        page.fill("#stacked-email", user)
        page.fill("#stacked-password", password)
        res = solve(page, context)
        print(f"Challenge solved: {res.success}")
        page.locator("button.pure-button").first.click()
        page.wait_for_timeout(2500)
        names = [c["name"] for c in context.cookies() if c.get("name")]
        print("ok cookie_names=" + ",".join(names))


if __name__ == "__main__":
    main()
