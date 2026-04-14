---
name: agent-browser-fetcher
description: Fetch final rendered HTML through local Chromium (`uv run python -m app.fetch_html`) when plain HTTP/curl fails because of JavaScript rendering, redirect loops, geofencing, proxy requirements, or antibot interstitials. Use when OpenClaw needs saved HTML artifacts or inline HTML plus JSON status (`success|blocked|error`) for downstream decisions.
---

# Scope

Use this skill as a thin adapter over this repository only.

## Use This Skill

- Use when direct HTTP client or `curl` cannot get usable final HTML.
- Use when page behavior depends on real browser JS execution.
- Use when the page is sensitive to IP geography or needs browser-level proxying.
- Use when OpenClaw workflow needs JSON status plus HTML artifact path or inline `html`.

## Do Not Use This Skill

- Do not use for simple static pages where `curl`/HTTP client already returns correct HTML.
- Do not use as first step for every URL; keep it as fallback for hard pages.
- Do not use for multi-step UI automation; use browser automation tools for that.
- Do not promise antibot bypass.

# Supported Model

This fetcher has one supported execution model:

- start a local Chromium/Chrome process;
- optionally pass a browser-level proxy;
- open the URL;
- wait for rendered HTML;
- save HTML and/or return it inline in JSON.

Attach-to-existing-browser and context-level proxy flows are intentionally out of scope.

# Portable OpenClaw Contract

For reproducible use by another OpenClaw agent, assume these four layers:

1. Repository code in `{baseDir}`.
2. Runtime contract: `uv`, Chromium/Chrome, writable output path.
3. Secrets live outside git.
4. One recommended run path through wrapper or direct CLI.

## Preferred secret convention

Prefer one secret file outside git:

```bash
~/.openclaw/secrets/agent-browser-fetcher.env
```

Expected optional variables:

```bash
BROWSER_PROXY='socks5://user:pass@host:port'
BROWSER_EXECUTABLE_PATH='/path/to/chrome'
BROWSER_USER_DATA_DIR='/tmp/agent-browser-fetcher/browser-profile'
FETCHER_NO_SANDBOX=1
FETCHER_WARMUP_URL='https://example.com/'
```

Legacy fallback supported by wrapper only:

```bash
~/.openclaw/secrets/ozon-proxy.env
```

If present, `OZON_PROXY_URL` is mapped to `BROWSER_PROXY`.

## Bootstrap / validation

Before first use on a new machine or by a new agent:

```bash
cd "{baseDir}"
scripts/bootstrap_openclaw.sh
scripts/check_env.sh
```

# Preferred Execution Path

Start with the simplest working command.

```bash
cd "{baseDir}"
uv run python -m app.fetch_html "$URL" \
  --timeout 60 \
  --output-format openclaw \
  --save-html "$HTML_PATH"
```

If proxying is required, prefer browser-level proxying:

```bash
cd "{baseDir}"
uv run python -m app.fetch_html "$URL" \
  --proxy-server "$PROXY_URL" \
  --timeout 60 \
  --output-format openclaw \
  --save-html "$HTML_PATH"
```

Recommended wrapper path for OpenClaw:

```bash
cd "{baseDir}"
scripts/openclaw_fetch.sh "$URL" "$HTML_PATH"
```

The wrapper auto-loads, in order:
- `FETCHER_SECRET_FILE`
- `~/.openclaw/secrets/agent-browser-fetcher.env`
- `~/.openclaw/secrets/ozon-proxy.env` (legacy fallback)

# Useful Options

- `--browser-executable-path` — explicit Chromium/Chrome path.
- `--user-data-dir` — separate browser profile.
- `--proxy-server` — browser-level proxy, for example `socks5://user:pass@host:port`.
- `--warmup-url` — warm-up navigation before target URL.
- `--wait-selector` — treat page as ready when selector appears.
- `--headful` — disable headless.
- `--no-sandbox` — useful in some root/container environments.
- `--browser-arg` — extra Chromium flag.

# Inline Mode

Use only when caller explicitly wants HTML in memory instead of a saved artifact.

```bash
cd "{baseDir}"
uv run python -m app.fetch_html "$URL" \
  --timeout 60 \
  --output-format openclaw \
  --embed-html \
  --no-save-html
```

Expected output in this mode:
- `artifacts` is empty.
- `html` contains the rendered page.

# Success Criteria

Treat the run as success only when:

- `status == "success"`
- `result.ok == true`
- `result.blocked == false`
- `result.challenge_detected == false`
- in file mode: HTML artifact exists on disk
- in inline mode: `html` is non-empty

# Error Handling Contract

- Exit code `0`: success.
- Exit code `2`: blocked/challenge outcome.
- Exit code `1`: execution or fetch error.
- If stdout is not valid JSON, treat as hard error.
- If JSON says success in file mode but artifact file is missing, treat as error.
- If JSON says success in inline mode but `html` is empty, treat as error.

# Practical Guidance

- Prefer file mode by default.
- Add `--warmup-url` only when navigation is unstable.
- Add `--wait-selector` only when SPA content appears late.
- Prefer `--proxy-server` over custom low-level proxy hacks.
- Keep `--embed-html` off unless the caller explicitly needs inline HTML.

# Limitations

- Real browser execution does not guarantee antibot bypass.
- A site can still return challenge/blocked HTML.
- Success depends on IP reputation, proxy quality, and target defenses.
- If an official API exists, prefer the API over rendered HTML.

# Safety Notes

- Never leak secrets, tokens, cookies, or proxy credentials in responses.
- Keep proxy configuration outside the repository when possible.
- Keep behavior non-destructive: fetch page, write artifact, report JSON result.
