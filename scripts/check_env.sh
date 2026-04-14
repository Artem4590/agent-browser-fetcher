#!/usr/bin/env bash

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_SECRET_FILE="$HOME/.openclaw/secrets/agent-browser-fetcher.env"
LEGACY_SECRET_FILE="$HOME/.openclaw/secrets/ozon-proxy.env"
SECRET_FILE="${FETCHER_SECRET_FILE:-$DEFAULT_SECRET_FILE}"

status_ok() { printf 'OK   %s\n' "$1"; }
status_warn() { printf 'WARN %s\n' "$1"; }
status_err() { printf 'ERR  %s\n' "$1"; }

resolve_browser() {
  if [[ -n "${BROWSER_EXECUTABLE_PATH:-}" && -x "${BROWSER_EXECUTABLE_PATH}" ]]; then
    printf '%s\n' "$BROWSER_EXECUTABLE_PATH"
    return 0
  fi

  local candidate=""
  for candidate in \
    /home/openclaw/.local/bin/openclaw-chrome \
    "$(command -v google-chrome 2>/dev/null || true)" \
    "$(command -v google-chrome-stable 2>/dev/null || true)" \
    "$(command -v chromium 2>/dev/null || true)" \
    "$(command -v chromium-browser 2>/dev/null || true)"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

printf '== agent-browser-fetcher environment check ==\n'
printf 'repo: %s\n' "$REPO_DIR"

if command -v uv >/dev/null 2>&1; then
  status_ok "uv found: $(command -v uv)"
else
  status_err "uv not found"
fi

if command -v python3 >/dev/null 2>&1; then
  status_ok "python3 found: $(python3 --version 2>&1)"
else
  status_warn "python3 not found in PATH"
fi

if browser_path="$(resolve_browser)"; then
  status_ok "browser found: $browser_path"
else
  status_err "no Chromium/Chrome executable found"
fi

if [[ -f "$SECRET_FILE" ]]; then
  status_ok "secret file found: $SECRET_FILE"
elif [[ "$SECRET_FILE" != "$LEGACY_SECRET_FILE" && -f "$LEGACY_SECRET_FILE" ]]; then
  status_warn "standard secret file missing; legacy proxy file found: $LEGACY_SECRET_FILE"
else
  status_warn "no secret file found (optional unless target site needs proxy/geofenced access)"
fi

if [[ -f "$REPO_DIR/pyproject.toml" ]]; then
  status_ok "pyproject.toml present"
else
  status_err "pyproject.toml missing"
fi

if (cd "$REPO_DIR" && uv run python -m app.fetch_html --help >/dev/null 2>&1); then
  status_ok "fetcher CLI starts"
else
  status_err "fetcher CLI failed to start (run: cd '$REPO_DIR' && uv sync)"
fi

printf '\nRecommended secret convention:\n'
printf '  %s\n' "$DEFAULT_SECRET_FILE"
printf 'Expected variables (all optional):\n'
printf '  BROWSER_PROXY=...\n'
printf '  BROWSER_EXECUTABLE_PATH=...\n'
printf '  BROWSER_USER_DATA_DIR=...\n'
printf '  FETCHER_NO_SANDBOX=1\n'
printf '  FETCHER_WARMUP_URL=...\n'
