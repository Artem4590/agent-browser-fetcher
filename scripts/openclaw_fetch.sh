#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <url> [output_html_path]" >&2
  exit 1
fi

URL="$1"
OUTPUT_PATH="${2:-/app/output/result.html}"
DEFAULT_SECRET_FILE="$HOME/.openclaw/secrets/agent-browser-fetcher.env"
LEGACY_SECRET_FILE="$HOME/.openclaw/secrets/ozon-proxy.env"
SECRET_FILE="${FETCHER_SECRET_FILE:-$DEFAULT_SECRET_FILE}"

if [[ -f "$SECRET_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$SECRET_FILE"
fi

if [[ -z "${BROWSER_PROXY:-}" && -f "$LEGACY_SECRET_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$LEGACY_SECRET_FILE"
  if [[ -z "${BROWSER_PROXY:-}" && -n "${OZON_PROXY_URL:-}" ]]; then
    BROWSER_PROXY="$OZON_PROXY_URL"
  fi
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found" >&2
  exit 1
fi

args=(
  "$URL"
  --timeout "${FETCHER_TIMEOUT:-60}"
  --output-format openclaw
  --save-html "$OUTPUT_PATH"
)

if [[ -n "${BROWSER_EXECUTABLE_PATH:-}" ]]; then
  args+=(--browser-executable-path "$BROWSER_EXECUTABLE_PATH")
fi

if [[ -n "${BROWSER_USER_DATA_DIR:-}" ]]; then
  args+=(--user-data-dir "$BROWSER_USER_DATA_DIR")
fi

if [[ -n "${BROWSER_PROXY:-}" ]]; then
  args+=(--proxy-server "$BROWSER_PROXY")
fi

if [[ -n "${FETCHER_WARMUP_URL:-}" ]]; then
  args+=(--warmup-url "$FETCHER_WARMUP_URL")
fi

if [[ -n "${FETCHER_WAIT_SELECTOR:-}" ]]; then
  args+=(--wait-selector "$FETCHER_WAIT_SELECTOR")
fi

if [[ "${FETCHER_HEADFUL:-0}" == "1" ]]; then
  args+=(--headful)
fi

if [[ "${FETCHER_NO_SANDBOX:-0}" == "1" ]]; then
  args+=(--no-sandbox)
fi

UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}" uv run python -m app.fetch_html "${args[@]}"
