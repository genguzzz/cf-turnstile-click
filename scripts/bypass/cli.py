"""Unified CLI for shield-bypass operations."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from bypass.config import debug_log, is_debug
from bypass.errors import BypassError
from bypass.fingerprint import (
    extract_fingerprint,
    format_curl_cmd,
    format_python_code,
)
from bypass.injector import inject_script, isolated_eval, main_eval
from bypass.inspector import (
    describe_point,
    detect_page_state,
    dump_page_controls,
    inspect_iframes,
)
from bypass.plugins import PluginRegistry, auto_solve, detect_challenge
from bypass.session import (
    attach_cdp,
    pick_active_page,
    session_status,
    start_session,
    stop_session,
)


def _handle_session(args: argparse.Namespace) -> int:
    action = args.action
    if action == "start":
        meta = start_session(port=args.port)
        extra = f" display={meta.get('display')}" if meta.get("display") else ""
        print(f"ok cdp={meta['cdp']} pid={meta['pid']} profile={meta['profile']}{extra}")
        return 0

    if action == "stop":
        stop_session()
        print("ok stopped")
        return 0

    if action == "restart":
        stop_session()
        meta = start_session(port=args.port)
        print(f"ok restarted cdp={meta['cdp']} pid={meta['pid']}")
        return 0

    if action == "status":
        st = session_status()
        print(
            f"ok alive={st.get('alive')} cdp={st.get('cdp')} pid={st.get('pid')} "
            f"display={st.get('display') or '-'}"
        )
        return 0 if st.get("alive") else 1

    if action == "debug":
        cmd_str = " ".join(args.command) if isinstance(args.command, list) else (args.command or "")
        return _debug_loop(args.url, cmd_str)

    return 0


def _run_debug_command(page, ctx, line: str) -> None:
    line = line.strip()
    if not line:
        return

    if line.startswith("goto "):
        url = line[5:].strip()
        page.goto(url, wait_until="domcontentloaded")
        print(f"ok url={page.url} title={page.title()!r}", file=sys.stderr)
        return

    if line in ("detect", "state"):
        st = detect_page_state(page)
        detections = detect_challenge(page, ctx)
        det_names = [f"{d.challenge_type}({d.confidence:.2f})" for d in detections]
        print(
            f"ok url={st['url']}\n"
            f"   title={st['title']!r}\n"
            f"   detected_challenges={det_names}\n"
            f"   tokens={st['tokens']}\n"
            f"   total_iframes={st['total_iframes']}",
            file=sys.stderr,
        )
        return

    if line == "probe" or line == "iframes":
        iframes = inspect_iframes(page)
        print(f"ok found {len(iframes)} iframes:", file=sys.stderr)
        for f in iframes:
            print(
                f"  [{f['index']}] challenge={f['challenge_type']} "
                f"box={f['box']} src={f['src'][:80]!r} text={f['text'][:50]!r}",
                file=sys.stderr,
            )
        return

    if line == "controls":
        controls = dump_page_controls(page)
        print(f"ok {len(controls)} controls:", file=sys.stderr)
        for c in controls:
            print(f"  {c['selector']}[{c['index']}] id={c['id']!r} type={c['type']!r} box={c['box']}", file=sys.stderr)
        return

    if line == "solve":
        res = auto_solve(page, ctx)
        print(
            f"ok solve success={res.success} type={res.challenge_type} "
            f"token_len={len(res.token)} clearance={bool(res.clearance)} err={res.error}",
            file=sys.stderr,
        )
        return

    if line == "export":
        fp = extract_fingerprint(page, ctx)
        print(json.dumps(fp, indent=2, ensure_ascii=False))
        return

    if line == "pages":
        for i, p in enumerate(ctx.pages):
            try:
                print(f"ok page[{i}] url={p.url!r} title={p.title()!r}", file=sys.stderr)
            except Exception:
                pass
        return

    if line.startswith("shot"):
        parts = line.split(maxsplit=1)
        path = parts[1] if len(parts) > 1 else "/tmp/shield-bypass-debug.png"
        page.screenshot(path=path, full_page=True)
        print(f"ok screenshot saved to {path}", file=sys.stderr)
        return

    if line.startswith("iso "):
        js = line[4:].strip()
        try:
            res = isolated_eval(page, js)
            print(repr(res)[:500], file=sys.stderr)
        except Exception as e:
            print(f"eval error: {e}", file=sys.stderr)
        return

    if line.startswith("main "):
        js = line[5:].strip()
        try:
            res = main_eval(page, js)
            print(repr(res)[:500], file=sys.stderr)
        except Exception as e:
            print(f"eval error: {e}", file=sys.stderr)
        return

    print(f"unknown debug command: {line}", file=sys.stderr)


def _debug_loop(url: str, command: str) -> int:
    os.environ.setdefault("SHIELD_BYPASS_DEBUG", "1")
    with attach_cdp() as (page, ctx):
        page = pick_active_page(ctx, page)
        if url:
            page.goto(url, wait_until="domcontentloaded")
            print(f"ok url={page.url} title={page.title()!r}", file=sys.stderr)

        if command:
            _run_debug_command(page, ctx, command)
            return 0

        print(
            "Commands:\n"
            "  goto <url>      - Navigate to URL\n"
            "  detect / state  - Detect challenges and inspect state\n"
            "  iframes / probe - List all iframes and challenge frames\n"
            "  controls        - Dump interactive form controls\n"
            "  solve           - Auto-solve detected challenge\n"
            "  export          - Dump full fingerprint & tokens JSON\n"
            "  pages           - List open tabs\n"
            "  shot [path]     - Full page screenshot\n"
            "  iso <js>        - Evaluate JS in isolated context\n"
            "  main <js>       - Evaluate JS in main world\n"
            "  quit / exit     - Detach\n",
            file=sys.stderr,
        )

        while True:
            try:
                line = input("bypass> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("", file=sys.stderr)
                break
            if not line or line in ("quit", "exit"):
                break
            _run_debug_command(page, ctx, line)

    print("ok detached (browser session still running)", file=sys.stderr)
    return 0


def _handle_solve(args: argparse.Namespace) -> int:
    from bypass import solve_url

    res = solve_url(
        args.url,
        timeout_s=args.timeout,
        headless=args.headless,
        challenge_type=args.type,
    )
    if args.json:
        out = {
            "success": res.success,
            "challenge_type": res.challenge_type,
            "token": res.token,
            "clearance": res.clearance,
            "data": res.data,
            "error": res.error,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        if res.success:
            val = res.token or res.clearance or "solved"
            print(val)
        else:
            print(f"FAILED: {res.error}", file=sys.stderr)
            return 1
    return 0 if res.success else 1


def _handle_fetch(args: argparse.Namespace) -> int:
    from bypass import fetch_url

    data = fetch_url(
        args.url,
        timeout_s=args.timeout,
        headless=args.headless,
    )
    if args.title_only:
        print(f"PAGE_TITLE: {data['title']}")
        return 0

    print(f"PAGE_TITLE: {data['title']}", file=sys.stderr)
    if args.html:
        sys.stdout.write(data["html"])
    else:
        sys.stdout.write(data["text"])
    return 0


def _handle_export(args: argparse.Namespace) -> int:
    from bypass.browser import chrome_context

    with chrome_context(headless=args.headless) as (page, ctx):
        page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
        auto_solve(page, ctx, timeout_s=args.timeout)

        fp = extract_fingerprint(page, ctx)

        if args.format == "curl":
            out_text = format_curl_cmd(args.url, fp)
        elif args.format == "python":
            out_text = format_python_code(args.url, fp)
        elif args.format == "env":
            tokens = fp.get("tokens", {})
            lines = [f"COOKIE='{fp.get('cookie_header', '')}'"]
            for k, v in tokens.items():
                clean_k = k.upper().replace("-", "_")
                lines.append(f"{clean_k}='{v}'")
            out_text = "\n".join(lines)
        else:
            out_text = json.dumps(fp, indent=2, ensure_ascii=False)

        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(out_text + "\n", encoding="utf-8")
            print(f"ok exported to {args.output}", file=sys.stderr)
        else:
            print(out_text)

    return 0


def _handle_inspect(args: argparse.Namespace) -> int:
    from bypass.browser import chrome_context

    with chrome_context(headless=args.headless) as (page, ctx):
        page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
        state = detect_page_state(page)
        detections = detect_challenge(page, ctx)
        iframes = inspect_iframes(page)
        controls = dump_page_controls(page)

        report = {
            "url": page.url,
            "title": page.title(),
            "detected_challenges": [
                {"type": d.challenge_type, "confidence": d.confidence, "details": d.details}
                for d in detections
            ],
            "tokens": state.get("tokens", {}),
            "iframes": iframes,
            "controls_count": len(controls),
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _handle_inject(args: argparse.Namespace) -> int:
    from bypass.browser import chrome_context

    with chrome_context(headless=args.headless) as (page, ctx):
        page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
        res = inject_script(
            page,
            args.js,
            world=args.world,
            frame_index=args.frame_index,
        )
        print(json.dumps(res, indent=2, default=str, ensure_ascii=False))
    return 0


def _handle_plugins(args: argparse.Namespace) -> int:
    plugins = PluginRegistry.list_plugins()
    print(f"Registered Plugins ({len(plugins)}):")
    for p in plugins:
        print(f"  - [{p['priority']:03d}] {p['name']:<18} ({p['display_name']})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shield-bypass",
        description="Unified Anti-Bot Challenge Bypass & Stealth Browser Automation CLI",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # session
    p_session = subparsers.add_parser("session", help="Manage background CDP session")
    p_session.add_argument("action", choices=["start", "stop", "restart", "status", "debug"])
    p_session.add_argument(
        "command",
        nargs="*",
        default=[],
        help="debug: probe | solve | state | iframes | export | shot | iso | main",
    )
    p_session.add_argument("--url", default="", help="Navigate before executing debug command")
    p_session.add_argument("--port", type=int, default=None, help="CDP port")

    # solve
    p_solve = subparsers.add_parser("solve", help="Open URL and solve anti-bot challenge")
    p_solve.add_argument("url", help="Target URL")
    p_solve.add_argument("--type", default=None, help="Force challenge type (cf_turnstile, cf_waf, recaptcha, hcaptcha)")
    p_solve.add_argument("--timeout", type=int, default=45, help="Timeout in seconds")
    p_solve.add_argument("--headless", action="store_true", help="Run in headless mode")
    p_solve.add_argument("--json", action="store_true", help="Output JSON structure")

    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Bypass challenge and fetch page text/html")
    p_fetch.add_argument("url", help="Target URL")
    p_fetch.add_argument("--timeout", type=int, default=45, help="Timeout in seconds")
    p_fetch.add_argument("--headless", action="store_true", help="Run in headless mode")
    p_fetch.add_argument("--html", action="store_true", help="Output full HTML instead of body text")
    p_fetch.add_argument("--title-only", action="store_true", help="Print only page title")

    # export
    p_export = subparsers.add_parser("export", help="Export full browser fingerprint, cookies, and tokens")
    p_export.add_argument("url", help="Target URL")
    p_export.add_argument("--timeout", type=int, default=45, help="Timeout in seconds")
    p_export.add_argument("--headless", action="store_true", help="Run in headless mode")
    p_export.add_argument("--format", choices=["json", "curl", "python", "env"], default="json")
    p_export.add_argument("-o", "--output", help="Write export output to file")

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect page iframes, DOM controls, and challenge state")
    p_inspect.add_argument("url", help="Target URL")
    p_inspect.add_argument("--timeout", type=int, default=45, help="Timeout in seconds")
    p_inspect.add_argument("--headless", action="store_true", help="Run in headless mode")

    # inject
    p_inject = subparsers.add_parser("inject", help="Dynamically inject JS into page or iframe")
    p_inject.add_argument("url", help="Target URL")
    p_inject.add_argument("--js", required=True, help="JavaScript code to execute")
    p_inject.add_argument("--world", choices=["isolated", "main"], default="isolated")
    p_inject.add_argument("--frame-index", type=int, default=None, help="Target specific iframe index")
    p_inject.add_argument("--timeout", type=int, default=45, help="Timeout in seconds")
    p_inject.add_argument("--headless", action="store_true", help="Run in headless mode")

    # plugins
    p_plugins = subparsers.add_parser("plugins", help="List registered solver plugins")
    p_plugins.add_argument("action", choices=["list"])

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        os.environ["SHIELD_BYPASS_DEBUG"] = "1"
        os.environ["CF_TURNSTILE_DEBUG"] = "1"

    handlers = {
        "session": _handle_session,
        "solve": _handle_solve,
        "fetch": _handle_fetch,
        "export": _handle_export,
        "inspect": _handle_inspect,
        "inject": _handle_inject,
        "plugins": _handle_plugins,
    }

    handler = handlers.get(args.subcommand)
    if not handler:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except BypassError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
