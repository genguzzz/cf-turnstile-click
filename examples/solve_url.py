"""Open a page that already has Turnstile, solve, print token.

    python examples/solve_url.py https://example.com/login
"""

from __future__ import annotations

import sys

from cfturnstile import solve_url


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python examples/solve_url.py <url>", file=sys.stderr)
        raise SystemExit(2)
    print(solve_url(sys.argv[1]))


if __name__ == "__main__":
    main()
