#!/usr/bin/env bash
# shield-bypass: Unified CLI launcher for anti-bot bypass & stealth browser automation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

_find_python() {
  if [[ -n "${PYTHON_EXE:-}" && -x "$PYTHON_EXE" ]]; then
    echo "$PYTHON_EXE"
    return 0
  fi

  # 1. NS_CLIENT_ROOT override
  if [[ -n "${NS_CLIENT_ROOT:-}" && -x "${NS_CLIENT_ROOT}/.venv/bin/python" ]]; then
    echo "${NS_CLIENT_ROOT}/.venv/bin/python"
    return 0
  fi

  # 2. Walk up physical path to find common/skills/nodeseek/client/.venv
  local d
  d="$(cd "$SKILL_DIR" && pwd -P)"
  while [[ -n "$d" ]]; do
    if [[ -x "$d/common/skills/nodeseek/client/.venv/bin/python" ]]; then
      echo "$d/common/skills/nodeseek/client/.venv/bin/python"
      return 0
    fi
    [[ "$d" == "/" ]] && break
    d="$(dirname "$d")"
  done

  # 3. Check adjacent nodeseek/client/.venv
  if [[ -x "$SKILL_DIR/../nodeseek/client/.venv/bin/python" ]]; then
    echo "$SKILL_DIR/../nodeseek/client/.venv/bin/python"
    return 0
  fi

  # 4. Check global/home venvs
  for p in "$HOME/.venv/bin/python" "/root/.venv/bin/python"; do
    if [[ -x "$p" ]]; then
      echo "$p"
      return 0
    fi
  done

  # 5. System python3 fallback
  if command -v python3 >/dev/null 2>&1; then
    echo "$(command -v python3)"
    return 0
  fi

  return 1
}

PY="$(_find_python)" || {
  echo '{"ok":false,"error":"Python executable not found. Please set PYTHON_EXE."}' >&2
  exit 1
}

export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}"
exec "$PY" -m bypass.cli "$@"
