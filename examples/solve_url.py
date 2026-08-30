#!/usr/bin/env python3
"""Example: Auto-detect and solve any anti-bot challenge on a URL."""

import json
import sys
from pathlib import Path

# Add scripts directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from bypass import solve_url


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 solve_url.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"Solving challenges on: {url}...")
    res = solve_url(url, timeout_s=45)

    print("\n--- Solve Result ---")
    print(f"Success: {res.success}")
    print(f"Challenge Type: {res.challenge_type}")
    if res.token:
        print(f"Token Length: {len(res.token)}")
    if res.clearance:
        print(f"Clearance Cookie: {res.clearance[:20]}...")
    if res.error:
        print(f"Error: {res.error}")


if __name__ == "__main__":
    main()
