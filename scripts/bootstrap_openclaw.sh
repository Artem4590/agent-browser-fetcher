#!/usr/bin/env bash

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS_DIR="$HOME/.openclaw/secrets"
SECRET_FILE="${FETCHER_SECRET_FILE:-$SECRETS_DIR/agent-browser-fetcher.env}"

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

if [[ ! -f "$SECRET_FILE" ]]; then
  cat > "$SECRET_FILE" <<'EOF'
# agent-browser-fetcher runtime config
# Keep this file outside git. Recommended permissions: 600.

# Optional browser-level proxy, for example:
# BROWSER_PROXY='socks5://user:pass@host:port'

# Optional explicit browser path:
# BROWSER_EXECUTABLE_PATH='/home/openclaw/.local/bin/openclaw-chrome'

# Optional persistent profile path:
# BROWSER_USER_DATA_DIR='/tmp/agent-browser-fetcher/browser-profile'

# Useful in some root/container environments:
# FETCHER_NO_SANDBOX=1

# Optional warm-up URL for unstable targets:
# FETCHER_WARMUP_URL='https://example.com/'
EOF
  chmod 600 "$SECRET_FILE"
  echo "Created secret template: $SECRET_FILE"
else
  chmod 600 "$SECRET_FILE"
  echo "Secret file already exists: $SECRET_FILE"
fi

cd "$REPO_DIR"
uv sync

cat <<EOF

Bootstrap complete.

Next steps:
1. Edit secret file if you need proxy/browser overrides:
   $SECRET_FILE
2. Validate environment:
   cd "$REPO_DIR" && scripts/check_env.sh
3. Run fetcher through wrapper:
   cd "$REPO_DIR" && scripts/openclaw_fetch.sh "https://example.com" "/tmp/page.html"

The wrapper auto-loads, in order:
- FETCHER_SECRET_FILE (if set)
- ~/.openclaw/secrets/agent-browser-fetcher.env
- ~/.openclaw/secrets/ozon-proxy.env (legacy fallback)
EOF
