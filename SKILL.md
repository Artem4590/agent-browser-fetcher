---
name: agent-browser-fetcher
description: Fetch final rendered HTML through local `agent-browser-fetcher` (`uv run python -m app.fetch_html`) when plain HTTP/curl fails because of JS rendering, redirect loops, challenge, or antibot pages. Use for OpenClaw flows that require `--output-format openclaw`, saved HTML artifacts, and JSON-driven decisions by `status/result/artifacts`, in local mode or by attaching to runtime `127.0.0.1:9222`.
metadata:
  requires:
    - uv
    - python>=3.12,<3.14
    - app/fetch_html.py
    - scripts/openclaw_fetch.sh
    - chromium runtime locally or reachable CDP runtime at 127.0.0.1:9222
---

# Scope

Use this skill as a thin adapter over this repository only. Do not invent a new runtime.

## Use This Skill

- Use when direct HTTP client or `curl` cannot get usable final HTML.
- Use when page behavior depends on real browser JS execution.
- Use when there are redirect loops, challenge pages, or antibot interstitials.
- Use when OpenClaw workflow needs JSON status plus HTML artifact path.

## Do Not Use This Skill

- Do not use for simple static pages where `curl`/HTTP client already returns correct HTML.
- Do not use as first step for every URL; keep it as fallback for hard pages.
- Do not use for antibot bypass promises or guaranteed unlock flows.

# Prereqs

- Run from repository root: `agent-browser-fetcher/`.
- `uv` must be available in `PATH`.
- Python must satisfy `>=3.12,<3.14`.
- Project dependencies must be installed (`uv sync` done before first run).
- Output path for `--save-html` must be writable.
- For attach mode, runtime must expose CDP at `127.0.0.1:9222`.

# Preferred Execution Path

Always start with minimal safe command. Add extra flags only if needed.

1. Local mode (first try):

```bash
uv run python -m app.fetch_html "$URL" \
  --timeout 60 \
  --output-format openclaw \
  --save-html "$HTML_PATH"
```

2. Optional shell wrapper (same local intent):

```bash
scripts/openclaw_fetch.sh "$URL" "$HTML_PATH"
```

3. Read stdout JSON and decide from:
- `status`
- `result.ok`
- `result.blocked`
- `result.challenge_detected`
- `artifacts[]`

4. Treat as success only when:
- `status == "success"`
- `result.ok == true`
- `result.blocked == false`
- `result.challenge_detected == false`
- HTML artifact exists on disk.

# Fallback Path (Attach to Existing Browser Runtime)

Use when local start is unstable, slow, or blocked by local browser startup constraints.

```bash
uv run python -m app.fetch_html "$URL" \
  --connect-host 127.0.0.1 \
  --connect-port 9222 \
  --timeout 60 \
  --output-format openclaw \
  --save-html "$HTML_PATH"
```

Use advanced flags incrementally, not upfront:

- Add `--wait-selector "<selector>"` only when SPA content appears late.
- Add `--warmup-url "<url>"` only when target navigation is unstable.
- Add `--context-proxy-server "<proxy-or-list>"` only when network route requires proxy.
- Add `--headful` only for debugging/visual inspection.
- Keep `--no-context`, `--no-default-browser-flags`, `--browser-arg`, `--user-data-dir` for explicit troubleshooting cases only.

# Safe Defaults

- Always set `--output-format openclaw`.
- Always set `--save-html` to a concrete path.
- Use timeout around `60` seconds for hard pages.
- Keep `--embed-html` disabled by default.
- Start without warmup/wait-selector/proxy/headful.
- Write only the output HTML file; avoid any unrelated filesystem changes.

# Stdin JSON Mode

Use only when pipeline already builds JSON input.

```bash
cat << 'JSON' | uv run python -m app.fetch_html --stdin-json
{
  "url": "https://example.com",
  "timeout": 60,
  "output_format": "openclaw",
  "save_html": "/tmp/page.html"
}
JSON
```

# Error Handling Contract

- Exit code `0`: successful fetch path (`result.ok=true` expected).
- Exit code `2`: blocked/challenge outcome; do not mark as success.
- Exit code `1`: execution or fetch error.
- If stdout is not valid JSON, treat as hard error.
- If JSON says success but artifact file is missing, treat as error.
- If page is empty or too small, retry once with `--wait-selector` and/or longer timeout.

# Limitations

- Real browser execution does not guarantee antibot bypass.
- Response can still be challenge/blocked HTML.
- Quality depends on IP reputation, proxy quality, and target defenses.
- Runtime must have workable Chromium/CDP environment.

# Troubleshooting

## `uv not found`

- Check: `command -v uv`.
- If missing, stop and report unmet prerequisite; do not replace runtime with ad-hoc alternatives.

## Browser runtime unavailable

- For attach mode, check endpoint:
  `curl -sS http://127.0.0.1:9222/json/version`.
- If unreachable, start/fix browser runtime first or use local mode without `--connect-host/--connect-port`.

## Challenge or blocked page returned

- Do not report success.
- Keep outcome as blocked/error using JSON status.
- Retry with minimal targeted changes only: `--warmup-url`, then optional proxy.

## HTML saved but page is empty / SPA not rendered

- Add `--wait-selector "main"` (or specific app root selector).
- Increase `--timeout` (for example to `90`) and keep `--save-html`.
- Re-run without `--embed-html`; inspect saved artifact file directly.

## Proxy does not work

- Validate proxy format in `--context-proxy-server` (e.g. `http://host:port`).
- Try one known-good proxy before passing a list.
- If authenticated proxy is used, never print credentials in outputs.

# Safety Notes

- Never promise antibot bypass.
- Never claim success when JSON reports blocked/challenge/error.
- Do not embed full HTML into JSON unless explicitly needed.
- Do not leak secrets, tokens, cookies, or proxy credentials in agent responses.
- Keep behavior non-destructive: fetch page, write artifact, report JSON result.
