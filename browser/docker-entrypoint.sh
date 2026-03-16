#!/bin/bash

# Fail fast on command errors, unset vars, and pipeline failures.
set -euo pipefail

# Build an optional Chromium proxy flag from the PROXY env var.
PROXY_SERVER_SWITCH=""
if [ -n "${PROXY:-}" ]; then
  PROXY_SERVER_SWITCH="--proxy-server=${PROXY}"
fi

# Start Chromium under Xvfb, expose CDP, and use a temporary browser profile.
xvfb-run -a chromium \
  --remote-allow-origins=* \
  --no-first-run \
  --no-service-autorun \
  --no-default-browser-check \
  --homepage=about:blank \
  --no-pings \
  --password-store=basic \
  --disable-infobars \
  --disable-gpu \
  --disable-breakpad \
  --disable-component-update \
  --disable-backgrounding-occluded-windows \
  --disable-renderer-backgrounding \
  --disable-background-networking \
  --disable-dev-shm-usage \
  --disable-features=IsolateOrigins,site-per-process \
  --disable-session-crashed-bubble \
  --disable-search-engine-choice-screen \
  --blink-settings=imagesEnabled=false \
  --disable-site-isolation-trials \
  --process-per-site \
  --disable-application-cache \
  --disk-cache-size=0 \
  --start-maximized \
  --window-size=1920,1080 \
  --window-position=0,0 \
  --no-sandbox \
  --user-data-dir="$(mktemp -d)" \
  ${PROXY_SERVER_SWITCH} \
  --remote-debugging-port="${PORT:-9222}" \
  about:blank
