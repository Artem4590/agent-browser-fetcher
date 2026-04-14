# agent-browser-fetcher

Утилита для получения **итогового отрендеренного HTML через локальный Chromium**.

## Для чего нужна

Используйте fetcher, когда обычный HTTP-клиент (`curl`, `requests`) не даёт полезный HTML:

- страница рендерится через JavaScript;
- есть redirect-loop или нестабильная навигация;
- сайт зависит от географии / IP / прокси;
- нужно сохранить финальный DOM в файл и получить машинно-читаемый статус.

Fetcher **не** предназначен для сложной UI-автоматизации и не заменяет полноценный browser automation.

## Основная схема

Поднять собственный Chromium, при необходимости дать ему прокси, открыть URL, дождаться готовности страницы и вернуть:

- HTML-файл;
- JSON-результат (`success`, `blocked`, `error`);
- сетевую диагностику (`redirect_hops`, `status_counter`).

## Быстрый старт

```bash
uv sync
uv run python -m app.fetch_html "https://example.com" \
  --output-format openclaw \
  --save-html /tmp/page.html
```

## Если нужен прокси

Рекомендуемый способ — прокси на уровне самого браузера:

```bash
uv run python -m app.fetch_html "https://example.com" \
  --proxy-server "socks5://user:pass@host:port" \
  --output-format openclaw \
  --save-html /tmp/page.html
```

## Когда нужен прогрев или ожидание селектора

```bash
uv run python -m app.fetch_html "https://example.com/app" \
  --warmup-url "https://example.com" \
  --wait-selector "main" \
  --output-format openclaw \
  --save-html /tmp/page.html
```

## Inline-режим

Если HTML не нужно писать в файл:

```bash
uv run python -m app.fetch_html "https://example.com" \
  --output-format openclaw \
  --embed-html \
  --no-save-html
```

## Shell-обёртка для OpenClaw

```bash
scripts/openclaw_fetch.sh "https://example.com" "/tmp/page.html"
```

Полезные env-переменные для обёртки:

- `BROWSER_EXECUTABLE_PATH`
- `BROWSER_USER_DATA_DIR`
- `BROWSER_PROXY`
- `FETCHER_WARMUP_URL`
- `FETCHER_WAIT_SELECTOR`
- `FETCHER_TIMEOUT`
- `FETCHER_HEADFUL=1`
- `FETCHER_NO_SANDBOX=1`

## Полезные флаги

- `--browser-executable-path` — явный путь к Chromium/Chrome.
- `--user-data-dir` — отдельный профиль браузера.
- `--proxy-server` — прокси на уровне Chromium.
- `--browser-arg` — дополнительный аргумент Chromium.
- `--warmup-url` — прогревочная навигация перед целевым URL.
- `--wait-selector` — считать страницу готовой, когда появился селектор.
- `--headful` — отключить headless.
- `--no-sandbox` — нужно в некоторых окружениях/container root.
- `--embed-html` + `--no-save-html` — вернуть HTML прямо в JSON.

## Формат `--output-format openclaw`

```json
{
  "status": "success|blocked|error",
  "message": "...",
  "artifacts": [
    {"type": "html", "path": "/abs/path/page.html"}
  ],
  "result": {
    "ok": true,
    "blocked": false,
    "challenge_detected": false,
    "requested_url": "...",
    "final_url": "...",
    "html_bytes": 12345,
    "redirect_hops": [],
    "response_count": 10,
    "status_counter": {"200": 8, "307": 2},
    "error": null
  }
}
```

Если включить `--no-save-html`, массив `artifacts` будет пустым, а HTML вернётся в поле `html` только при `--embed-html`.

## Ограничения

- Fetcher не гарантирует обход антибота.
- При плохой IP-репутации или неподходящей географии сайт может отдавать challenge даже через браузер.
- Если есть нормальный официальный API, лучше использовать его, а не HTML.
