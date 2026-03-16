#!/usr/bin/env bash

# Fail fast on command errors, unset vars, and pipeline failures.
set -euo pipefail

# Require at least the target URL argument.
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <url> [output_html_path]" >&2
  exit 1
fi

URL="$1"
# Default output path can be overridden by the second positional argument.
OUTPUT_PATH="${2:-/app/output/result.html}"

# Run the fetcher through uv to use the project-managed Python environment.
if command -v uv >/dev/null 2>&1; then
  UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}" uv run python -m app.fetch_html \
    "$URL" \
    --timeout 60 \
    --output-format openclaw \
    --save-html "$OUTPUT_PATH"
else
  echo "uv not found" >&2
  exit 1
fi
