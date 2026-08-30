#!/usr/bin/env python3
"""Example: Solve challenge, export complete browser fingerprint, and replay request with curl_cffi."""

import json
import sys
from pathlib import Path

# Add scripts directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from bypass import auto_solve, chrome_context, extract_fingerprint, format_curl_cmd


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 export_fingerprint.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"Exporting fingerprint and session from: {url}...")

    with chrome_context(headless=False) as (page, ctx):
        page.goto(url, wait_until="domcontentloaded")
        solve_res = auto_solve(page, ctx, timeout_s=45)
        print(f"Challenge solved: {solve_res.success} ({solve_res.challenge_type})")

        fp = extract_fingerprint(page, ctx)

        # 1. Print structured JSON summary
        print("\n--- Fingerprint Summary ---")
        print(f"User-Agent: {fp['fingerprint']['navigator']['userAgent']}")
        print(f"Platform: {fp['fingerprint']['navigator']['platform']}")
        print(f"Canvas Hash: {fp['fingerprint']['canvasHash']}")
        print(f"Tokens: {list(fp['tokens'].keys())}")
        print(f"Cookies Count: {len(fp['cookies'])}")

        # 2. Print ready-to-run curl command
        print("\n--- Equivalent cURL Command ---")
        print(format_curl_cmd(url, fp))


if __name__ == "__main__":
    main()
