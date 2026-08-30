#!/usr/bin/env bash
# Backward compatibility wrapper for cf-turnstile. Forwards to bypass.sh.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$SCRIPT_DIR/bypass.sh" "$@"
