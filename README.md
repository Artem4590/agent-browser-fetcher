# agent-browser-fetcher

Легковесный воркер для получения итогового HTML через реальный Chromium + `nodriver`.

## Что решает

- `curl -L` уходит в бесконечные редиректы (`?__rr=...`) на `docs.ozon.ru`.
- Этот воркер открывает URL через браузерный runtime, сохраняет HTML в файл или возвращает его inline в JSON.
- Выводит структурированный JSON, удобный для агента OpenClaw.

## Стек

- Python 3.12
- `uv` (управление зависимостями/запуск)
- `nodriver` (CDP-клиент), форк: `https://github.com/CusDeb-Solutions/nodriver` (`sync-latest-updates`)
- Отдельный Chromium runtime (Docker `browser` сервис + CDP attach из `fetcher`)

## Архитектурные решения

- Отдельный браузерный контейнер и подключение к нему через `--connect-host/--connect-port`.
- Chromium под `xvfb-run` с набором анти-фоновых/кэш/рендер флагов.
- Использование `browser.create_context()` перед навигацией (как изолированный browser context).
- Поддержка прокси на уровне browser runtime (`BROWSER_PROXY`) и context (`--context-proxy-server`).

## Быстрый старт (локально)

```bash
uv sync
uv run python -m app.fetch_html "https://docs.ozon.ru/api/seller/en/" --output-format openclaw
```

По умолчанию HTML сохраняется в `./output/<timestamp>-<url>.html`.

## Линтинг

```bash
uv run ruff check app
```

## Быстрый старт (Docker)

```bash
docker compose build
docker compose up -d browser
docker compose run --rm fetcher
docker compose down
```

Результат HTML будет в `./output/ozon.html`.
`docker-compose.yml` использует `network_mode: host` для `browser` и `fetcher`, чтобы максимально приблизить сетевое поведение к "обычному" браузеру.

## Вызов из OpenClaw

### Рекомендуемый режим (быстро + надежно)

1. Сначала использовать хостовый браузер OpenClaw для обычной навигации и извлечения.
2. Подключать `agent-browser-fetcher` только для страниц вне доступа (таймауты, блокировки, challenge, redirect loop).
3. Для fallback использовать skill-скрипт:

```bash
skills/agent-browser-fetcher/scripts/fetch_fallback.sh "https://example.com" "/tmp/page.html"
```

Такой режим сохраняет скорость поиска: основной трафик идёт через хостовый браузер, а тяжелый fetcher включается только по необходимости.


### Вариант 1: прямой запуск (локально)

```bash
uv run python -m app.fetch_html "https://docs.ozon.ru/api/seller/en/" \
  --output-format openclaw \
  --save-html /tmp/ozon.html
```

### Вариант 1b: вернуть HTML сразу в JSON (без записи файла)

```bash
uv run python -m app.fetch_html "https://docs.ozon.ru/api/seller/en/" \
  --output-format openclaw \
  --embed-html \
  --no-save-html
```

### Вариант 2: shell-обертка

```bash
scripts/openclaw_fetch.sh "https://docs.ozon.ru/api/seller/en/" "/tmp/ozon.html"
```

### Вариант 3: JSON через stdin (удобно для агентных пайплайнов)

```bash
cat << 'JSON' | uv run python -m app.fetch_html --stdin-json
{
  "url": "https://docs.ozon.ru/api/seller/en/",
  "timeout": 60,
  "output_format": "openclaw",
  "no_save_html": true,
  "embed_html": true,
  "wait_selector": "main"
}
JSON
```

## Формат выхода `--output-format openclaw`

```json
{
  "status": "success|blocked|error",
  "message": "...",
  "artifacts": [{ "type": "html", "path": "/abs/path/page.html" }],
  "html": "<!doctype html>...",
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

## Полезные флаги

- `--wait-selector "main"` — успех, когда найден селектор (если страница SPA).
- `--connect-host 127.0.0.1 --connect-port 9222` — подключение к уже запущенному браузеру.
- `--warmup-url "https://docs.ozon.ru/"` — прогревочная навигация перед целевым URL.
- `--context-proxy-server "http://p1:8080,http://p2:8080"` — прокси для browser context (если список, берётся случайный).
- `--no-context` — отключить `create_context()` и использовать `main_tab`.
- `--no-default-browser-flags` — отключить преднастроенный профиль Chromium-флагов.
- `--user-data-dir /path/to/profile` — reuse профиля/куки.
- `--headful` — отключить headless.
- `--embed-html` — встраивать HTML прямо в JSON (обычно не нужно).
- `--no-save-html` — не записывать HTML в файл (для inline-режима с `--embed-html`).
- `--browser-arg "--proxy-server=http://..."` — кастомный прокси.

## Ограничения

- Если IP/сеть помечены антиботом, можно получить challenge/blocked HTML даже через браузер.
- `nodriver` лицензирован под AGPL-3.0; учитывайте это для прод-интеграции.
