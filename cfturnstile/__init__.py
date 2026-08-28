"""Drop-in Cloudflare Turnstile checkbox solver for Patchright / Playwright.

Typical use::

    from cfturnstile import chrome_context, solve

    with chrome_context() as (page, context):
        page.goto("https://example.com/login")
        token = solve(page)
        # fill the rest of the form, then submit
"""

from cfturnstile.browser import chrome_context, extension_dir, launch_extension_args, launch_kwargs
from cfturnstile.errors import TurnstileError
from cfturnstile.solver import isolated_eval, solve, solve_url

__all__ = [
    "TurnstileError",
    "chrome_context",
    "extension_dir",
    "isolated_eval",
    "launch_extension_args",
    "launch_kwargs",
    "solve",
    "solve_url",
]

__version__ = "0.1.0"
