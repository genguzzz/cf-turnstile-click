from __future__ import annotations

import argparse
import os
import sys

from cfturnstile.errors import TurnstileError


def _session_main(argv: list[str]) -> int:
    from cfturnstile.session import session_status, start_session, stop_session

    parser = argparse.ArgumentParser(prog="cf-turnstile session")
    parser.add_argument("action", choices=["start", "stop", "status", "debug"])
    parser.add_argument(
        "command",
        nargs="?",
        default="",
        help="debug: probe | solve | state | shot | pages (omit for interactive)",
    )
    parser.add_argument("--url", default="", help="debug: navigate before the command")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.verbose:
        os.environ["CF_TURNSTILE_DEBUG"] = "1"
    if args.action == "start":
        meta = start_session()
        extra = ""
        if meta.get("display"):
            extra = f" display={meta['display']}"
        print(f"ok cdp={meta['cdp']} pid={meta['pid']} profile={meta['profile']}{extra}")
        return 0
    if args.action == "stop":
        stop_session()
        print("ok stopped")
        return 0
    if args.action == "status":
        st = session_status()
        print(
            f"ok alive={st.get('alive')} cdp={st.get('cdp')} pid={st.get('pid')} "
            f"display={st.get('display') or '-'}"
        )
        return 0 if st.get("alive") else 1
    return _debug_loop(args.url, args.command)


def _pick_page(ctx, page):
    from cfturnstile.solver import IFRAME_SEL

    for p in ctx.pages:
        try:
            if p.locator(IFRAME_SEL).count() > 0:
                return p
        except Exception:
            continue
    return page


def _run_debug_line(page, ctx, line: str) -> None:
    from cfturnstile.solver import (
        challenge_status,
        isolated_eval,
        log_iframes_and_checkbox,
        solve,
        widget_state,
    )

    if line.startswith("goto "):
        page.goto(line[5:].strip(), wait_until="domcontentloaded")
        print(f"ok url={page.url}", file=sys.stderr)
        return
    if line == "state":
        st = challenge_status(page)
        print(
            f"ok checkbox={st.get('checkbox')} success={st.get('success')} "
            f"verifying={st.get('verifying')} has_token={st.get('token')} "
            f"ext={widget_state(page)!r} url={page.url}",
            file=sys.stderr,
        )
        return
    if line == "shot":
        page.screenshot(path="/tmp/cf-turnstile-session.png", full_page=True)
        print("ok /tmp/cf-turnstile-session.png", file=sys.stderr)
        return
    if line == "probe":
        from cfturnstile.solver import dump_page_controls, log_iframes_and_checkbox

        os.environ["CF_TURNSTILE_DEBUG"] = "1"
        box = log_iframes_and_checkbox(page)
        dump_page_controls(page)
        print(f"ok target={box} status={challenge_status(page)}", file=sys.stderr)
        return
    if line == "solve":
        tok = solve(page)
        print(f"ok token_len={len(tok)}", file=sys.stderr)
        return
    if line == "pages":
        for i, p in enumerate(ctx.pages):
            print(f"ok page[{i}] url={p.url!r} title={(p.title() or '')!r}", file=sys.stderr)
        return
    if line.startswith("iso "):
        js = line[4:].strip()
        if not js.startswith("("):
            js = "() => (" + js + ")"
        print(repr(isolated_eval(page, js))[:300], file=sys.stderr)
        return
    print("unknown command", file=sys.stderr)


def _debug_loop(url: str, command: str) -> int:
    from cfturnstile.session import attach_cdp

    os.environ.setdefault("CF_TURNSTILE_DEBUG", "1")
    with attach_cdp() as (page, ctx):
        page = _pick_page(ctx, page)
        if url:
            page.goto(url, wait_until="domcontentloaded")
            print(f"ok url={page.url}", file=sys.stderr)
        if command:
            _run_debug_line(page, ctx, command.strip())
            return 0
        print(
            "commands: goto <url> | probe | solve | state | shot | pages | iso <js> | quit",
            file=sys.stderr,
        )
        while True:
            try:
                line = input("cf> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("", file=sys.stderr)
                break
            if not line or line in {"quit", "exit"}:
                break
            _run_debug_line(page, ctx, line)
    print("ok detached (chrome still running)", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "session":
        return _session_main(argv[1:])

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
        os.environ["CF_TURNSTILE_DEBUG"] = "1"
    from cfturnstile.solver import solve_url

    try:
        token = solve_url(args.url, timeout_s=args.timeout, headless=args.headless)
    except TurnstileError as e:
        print(str(e), file=sys.stderr)
        return 1
    sys.stdout.write(token + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
