"""Integrate into an existing Patchright script.

    python examples/existing_page.py
"""

from __future__ import annotations

from cfturnstile import chrome_context, solve


def main() -> None:
    with chrome_context() as (page, context):
        page.goto("https://nopecha.com/captcha/turnstile", wait_until="domcontentloaded")
        token = solve(page)
        print(f"token_len={len(token)}")
        _ = context


if __name__ == "__main__":
    main()
