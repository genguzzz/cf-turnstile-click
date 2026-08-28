from __future__ import annotations

import argparse
import sys

from cfturnstile.errors import TurnstileError
from cfturnstile.solver import solve_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cf-turnstile",
        description="Open a URL in patched Chrome, click the Turnstile checkbox, print the token.",
    )
    parser.add_argument("--url", required=True, help="Page that already renders a Turnstile widget")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--headless", action="store_true", help="Usually fails; headed is the default")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.verbose:
        import os

        os.environ["CF_TURNSTILE_DEBUG"] = "1"
    try:
        token = solve_url(args.url, timeout_s=args.timeout, headless=args.headless)
    except TurnstileError as e:
        print(str(e), file=sys.stderr)
        return 1
    sys.stdout.write(token + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
