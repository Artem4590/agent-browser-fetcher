"""Получение отрендеренного HTML через локальный Chromium + nodriver."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import nodriver as uc
from nodriver import cdp

LOGGER = logging.getLogger("fetch_html")

CHALLENGE_MARKERS = (
    "antibot challenge page",
    "fab_chlg_",
    "challenge-data",
    "please, enable javascript to continue",
    "пожалуйста, включите javascript",
)

BLOCK_BODY_MARKERS = (
    "доступ ограничен",
    "incident:",
    "служба поддержки",
    "your request has been blocked",
    "the requested url was rejected",
)

BLOCK_TITLE_MARKERS = (
    "access denied",
    "доступ ограничен",
    "request blocked",
)

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")

FAST_READY_AFTER_FIRST_HTML_SECONDS = 1.5
MIN_TEXT_CHARS_FOR_FAST_READY = 80
POST_READY_REFRESH_MAX_BYTES = 50_000

DEFAULT_BROWSER_ARGS = (
    "--remote-allow-origins=*",
    "--no-first-run",
    "--no-service-autorun",
    "--no-default-browser-check",
    "--homepage=about:blank",
    "--no-pings",
    "--password-store=basic",
    "--disable-infobars",
    "--disable-gpu",
    "--disable-breakpad",
    "--disable-component-update",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-networking",
    "--disable-dev-shm-usage",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-session-crashed-bubble",
    "--disable-search-engine-choice-screen",
    "--blink-settings=imagesEnabled=false",
    "--disable-site-isolation-trials",
    "--process-per-site",
    "--disable-application-cache",
    "--disk-cache-size=0",
    "--start-maximized",
    "--window-size=1920,1080",
    "--window-position=0,0",
)


@dataclass
class RedirectHop:
    """Описывает один шаг HTTP-редиректа для конкретного запроса."""

    request_id: str
    from_url: str
    to_url: str
    status: int | None
    location: str | None


@dataclass
class ResponseRecord:
    """Хранит зафиксированный сетевой ответ в рамках сессии браузера."""

    request_id: str
    url: str
    status: int
    mime_type: str
    resource_type: str


@dataclass
class FetchResult:
    """Содержит итог получения HTML, тайминги и сетевую диагностику."""

    ok: bool
    blocked: bool
    challenge_detected: bool
    requested_url: str
    final_url: str
    html_bytes: int
    started_at: str
    finished_at: str
    duration_ms: int
    saved_html_path: str | None = None
    error: str | None = None
    redirect_hops: list[RedirectHop] = field(default_factory=list)
    response_count: int = 0
    status_counter: dict[str, int] = field(default_factory=dict)


@dataclass
class FetchSettings:
    """Содержит параметры запуска сценария получения HTML."""

    url: str
    warmup_url: str | None
    timeout_seconds: float
    settle_seconds: float
    poll_interval: float
    min_html_bytes: int
    wait_selector: str | None
    headless: bool
    sandbox: bool
    browser_executable_path: str | None
    user_data_dir: str | None
    proxy_server: str | None
    use_default_browser_flags: bool
    browser_args: list[str]
    save_html: str | None
    output_format: str
    embed_html: bool


def _extract_location(headers: Any) -> str | None:
    if not headers:
        return None
    try:
        for key, value in dict(headers).items():
            if str(key).lower() == "location":
                return str(value)
    except Exception:
        return None
    return None


def _check_markers(html: str) -> tuple[bool, bool]:
    lower = html.lower()
    challenge = any(marker in lower for marker in CHALLENGE_MARKERS)
    blocked = any(marker in lower for marker in BLOCK_BODY_MARKERS)
    if not blocked:
        match = TITLE_RE.search(html)
        if match:
            title = " ".join(match.group(1).lower().split())
            blocked = any(marker in title for marker in BLOCK_TITLE_MARKERS)
    return challenge, blocked


def _as_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _ensure_parent(path: str) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def _merge_browser_args(*arg_lists: tuple[str, ...] | list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for arg_list in arg_lists:
        for arg in arg_list:
            if arg in seen:
                continue
            merged.append(arg)
            seen.add(arg)
    return merged


def _build_browser_args(settings: FetchSettings) -> list[str]:
    browser_args = list(settings.browser_args)
    if settings.use_default_browser_flags:
        browser_args = _merge_browser_args(list(DEFAULT_BROWSER_ARGS), browser_args)
    if settings.proxy_server and not any(arg.startswith("--proxy-server=") for arg in browser_args):
        browser_args.append(f"--proxy-server={settings.proxy_server}")
    if settings.headless and not any(arg.startswith("--headless") for arg in browser_args):
        browser_args.append("--headless=new")
    return browser_args


def _to_openclaw_payload(result: FetchResult, html: str | None) -> dict[str, Any]:
    status = "success" if result.ok else "blocked" if result.blocked else "error"
    artifacts: list[dict[str, Any]] = []
    if result.saved_html_path:
        artifacts.append({"type": "html", "path": result.saved_html_path})

    payload: dict[str, Any] = {
        "status": status,
        "message": (
            "HTML получен"
            if status == "success"
            else "Доступ к целевому URL ограничен антиботом"
            if status == "blocked"
            else "Ошибка получения HTML"
        ),
        "artifacts": artifacts,
        "result": asdict(result),
    }
    if html is not None:
        payload["html"] = html
    return payload


def _visible_text_len(html: str) -> int:
    without_code = SCRIPT_STYLE_RE.sub(" ", html)
    text = HTML_TAG_RE.sub(" ", without_code)
    return len(" ".join(text.split()))


async def fetch_html(settings: FetchSettings) -> tuple[FetchResult, str]:
    """Получает HTML страницы через локальный Chromium и возвращает HTML с метаданными."""
    started = time.time()
    started_mono = time.monotonic()
    redirect_hops: list[RedirectHop] = []
    responses: list[ResponseRecord] = []

    browser = None
    html = ""
    final_url = settings.url
    challenge_detected = False
    blocked = False
    rr_seen = False

    try:
        browser = await uc.start(
            headless=False,
            sandbox=settings.sandbox,
            browser_executable_path=settings.browser_executable_path,
            user_data_dir=settings.user_data_dir,
            browser_args=_build_browser_args(settings),
        )
        LOGGER.debug("stage=connect elapsed_ms=%d", int((time.monotonic() - started_mono) * 1000))

        tab = browser.main_tab

        if settings.warmup_url:
            try:
                await tab.get(settings.warmup_url)
                await tab.sleep(min(settings.settle_seconds, 2.0))
            except Exception:
                LOGGER.debug("Ошибка прогревочного запроса", exc_info=True)
        LOGGER.debug("stage=warmup elapsed_ms=%d", int((time.monotonic() - started_mono) * 1000))

        def on_request(ev: cdp.network.RequestWillBeSent, _tab: Any = None) -> None:
            if not ev.redirect_response:
                return
            redirect_hops.append(
                RedirectHop(
                    request_id=str(ev.request_id),
                    from_url=str(ev.redirect_response.url),
                    to_url=str(ev.request.url),
                    status=int(ev.redirect_response.status),
                    location=_extract_location(ev.redirect_response.headers),
                )
            )

        def on_response(ev: cdp.network.ResponseReceived, _tab: Any = None) -> None:
            responses.append(
                ResponseRecord(
                    request_id=str(ev.request_id),
                    url=str(ev.response.url),
                    status=int(ev.response.status),
                    mime_type=str(ev.response.mime_type or ""),
                    resource_type=str(ev.type_),
                )
            )

        tab.add_handler(cdp.network.RequestWillBeSent, on_request)
        tab.add_handler(cdp.network.ResponseReceived, on_response)
        await tab.send(cdp.network.enable())
        LOGGER.debug("stage=network_enable elapsed_ms=%d", int((time.monotonic() - started_mono) * 1000))
        tab = await tab.get(settings.url)
        LOGGER.debug("stage=navigate elapsed_ms=%d", int((time.monotonic() - started_mono) * 1000))

        deadline = time.monotonic() + settings.timeout_seconds
        ready = False
        first_html_seen_at: float | None = None
        first_html_logged = False
        last_html_bytes = 0
        stable_html_polls = 0

        while time.monotonic() < deadline:
            await tab.sleep(settings.poll_interval)
            try:
                await tab
                final_url = str(tab.url or final_url)
            except Exception:
                pass

            try:
                current_html = await tab.get_content()
            except Exception:
                continue

            if not current_html:
                continue

            html = current_html
            html_bytes = len(html.encode("utf-8"))
            if first_html_seen_at is None:
                first_html_seen_at = time.monotonic()
            if first_html_seen_at and not first_html_logged:
                LOGGER.debug(
                    "stage=first_html elapsed_ms=%d html_bytes=%d",
                    int((time.monotonic() - started_mono) * 1000),
                    html_bytes,
                )
                first_html_logged = True
            if abs(html_bytes - last_html_bytes) <= 128:
                stable_html_polls += 1
            else:
                stable_html_polls = 0
            last_html_bytes = html_bytes

            challenge, blocked_now = _check_markers(html)
            challenge_detected = challenge
            blocked = blocked_now

            if "__rr=" in final_url:
                rr_seen = True

            if settings.wait_selector:
                try:
                    elem = await tab.select(settings.wait_selector, timeout=0)
                except Exception:
                    elem = None
                ready = elem is not None and not blocked and not challenge
            else:
                has_closed_html = "</html" in html.lower()
                text_len = _visible_text_len(html)
                small_page_ready = (
                    has_closed_html and stable_html_polls >= 1 and text_len >= MIN_TEXT_CHARS_FOR_FAST_READY
                )
                fast_ready_elapsed = (
                    first_html_seen_at is not None
                    and (time.monotonic() - first_html_seen_at) >= FAST_READY_AFTER_FIRST_HTML_SECONDS
                    and text_len >= MIN_TEXT_CHARS_FOR_FAST_READY
                )
                ready = not challenge and not blocked and (
                    html_bytes >= settings.min_html_bytes or small_page_ready or fast_ready_elapsed
                )

            if ready:
                LOGGER.debug(
                    "stage=ready elapsed_ms=%d html_bytes=%d stable_polls=%d text_len=%d",
                    int((time.monotonic() - started_mono) * 1000),
                    html_bytes,
                    stable_html_polls,
                    _visible_text_len(html),
                )
                if settings.settle_seconds > 0:
                    await tab.sleep(settings.settle_seconds)
                should_refresh_after_settle = (
                    settings.wait_selector is not None or html_bytes < POST_READY_REFRESH_MAX_BYTES
                )
                if should_refresh_after_settle:
                    try:
                        html = await tab.get_content() or html
                    except Exception:
                        pass
                break

        if not html:
            raise RuntimeError("Не удалось получить HTML")

        challenge, blocked_now = _check_markers(html)
        challenge_detected = challenge
        blocked = blocked_now
        if rr_seen and (challenge or blocked or len(html.encode("utf-8")) < settings.min_html_bytes):
            challenge_detected = True

        ok = bool(html) and not blocked and not challenge_detected
        if settings.wait_selector and bool(html) and not blocked:
            ok = True

        finished = time.time()
        status_counter = Counter(str(item.status) for item in responses)
        result = FetchResult(
            ok=ok,
            blocked=blocked,
            challenge_detected=challenge_detected,
            requested_url=settings.url,
            final_url=final_url,
            html_bytes=len(html.encode("utf-8")),
            started_at=_as_iso(started),
            finished_at=_as_iso(finished),
            duration_ms=int((finished - started) * 1000),
            redirect_hops=redirect_hops,
            response_count=len(responses),
            status_counter=dict(status_counter),
        )

        if settings.save_html:
            path = str(Path(settings.save_html).expanduser().resolve())
            _ensure_parent(path)
            Path(path).write_text(html, encoding="utf-8")
            result.saved_html_path = path

        return result, html

    except Exception as exc:
        finished = time.time()
        result = FetchResult(
            ok=False,
            blocked=blocked,
            challenge_detected=challenge_detected,
            requested_url=settings.url,
            final_url=final_url,
            html_bytes=len(html.encode("utf-8")) if html else 0,
            started_at=_as_iso(started),
            finished_at=_as_iso(finished),
            duration_ms=int((finished - started) * 1000),
            error=f"{type(exc).__name__}: {exc}",
            redirect_hops=redirect_hops,
            response_count=len(responses),
            status_counter=dict(Counter(str(item.status) for item in responses)),
        )
        if settings.save_html and html:
            path = str(Path(settings.save_html).expanduser().resolve())
            _ensure_parent(path)
            Path(path).write_text(html, encoding="utf-8")
            result.saved_html_path = path
        return result, html

    finally:
        if browser is not None:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    uc.util.deconstruct_browser()
            except Exception:
                LOGGER.debug("Не удалось остановить браузер", exc_info=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Разбирает аргументы командной строки для утилиты получения HTML."""
    parser = argparse.ArgumentParser(description="Получение итогового HTML через локальный Chromium")
    parser.add_argument("url", nargs="?", help="Целевой URL")
    parser.add_argument("--stdin-json", action="store_true", help="Прочитать JSON-конфиг из stdin")
    parser.add_argument("--warmup-url", help="Опциональный URL для прогрева перед целевым")
    parser.add_argument("--timeout", type=float, default=45.0, help="Общий таймаут в секундах")
    parser.add_argument("--poll-interval", type=float, default=0.75, help="Интервал опроса")
    parser.add_argument("--settle-seconds", type=float, default=0.5, help="Дополнительное ожидание после готовности")
    parser.add_argument("--min-html-bytes", type=int, default=3000, help="Минимальный размер HTML для успеха")
    parser.add_argument("--wait-selector", help="Считать страницу готовой при наличии селектора")
    parser.add_argument("--headful", action="store_true", help="Отключить headless-режим")
    parser.add_argument("--no-sandbox", action="store_true", help="Передать sandbox=False в nodriver")
    parser.add_argument("--browser-executable-path", help="Явный путь к браузеру")
    parser.add_argument("--user-data-dir", help="Каталог постоянного браузерного профиля")
    parser.add_argument("--proxy-server", help="Прокси на уровне Chromium, например socks5://user:pass@host:port")
    parser.add_argument(
        "--no-default-browser-flags",
        action="store_true",
        help="Отключить стандартный профиль Chromium-флагов",
    )
    parser.add_argument("--browser-arg", action="append", default=[], help="Дополнительный аргумент браузера")
    parser.add_argument("--save-html", help="Путь для сохранения HTML")
    parser.add_argument(
        "--output-format",
        choices=("json", "openclaw"),
        default="json",
        help="Формат вывода в stdout",
    )
    parser.add_argument("--embed-html", action="store_true", help="Встраивать HTML в JSON-ответ")
    parser.add_argument(
        "--no-save-html",
        action="store_true",
        help="Не сохранять HTML в файл (используйте вместе с --embed-html для inline-режима)",
    )
    parser.add_argument("--verbose", action="store_true", help="Подробные debug-логи")
    return parser.parse_args(argv)


def _build_settings(args: argparse.Namespace) -> FetchSettings:
    data: dict[str, Any] = {}
    if args.stdin_json:
        data = json.load(sys.stdin)

    url = data.get("url") or args.url
    if not url:
        raise ValueError("URL обязателен (аргумент или stdin JSON)")

    no_save_html = bool(data.get("no_save_html", args.no_save_html))
    save_html = data.get("save_html") if "save_html" in data else args.save_html
    if no_save_html:
        save_html = None
    elif not save_html:
        stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        safe_url = re.sub(r"[^a-zA-Z0-9]+", "-", url)[:64].strip("-") or "page"
        save_html = str((Path("output") / f"{stamp}-{safe_url}.html").resolve())

    use_default_browser_flags = data.get("use_default_browser_flags")
    if use_default_browser_flags is None:
        use_default_browser_flags = not bool(
            data.get("no_default_browser_flags", args.no_default_browser_flags)
        )

    browser_args = data.get("browser_args")
    if browser_args is None:
        browser_args = list(args.browser_arg)
    elif isinstance(browser_args, str):
        browser_args = [browser_args]
    else:
        browser_args = list(browser_args)

    return FetchSettings(
        url=url,
        warmup_url=data.get("warmup_url") or args.warmup_url,
        timeout_seconds=float(data.get("timeout", args.timeout)),
        settle_seconds=float(data.get("settle_seconds", args.settle_seconds)),
        poll_interval=float(data.get("poll_interval", args.poll_interval)),
        min_html_bytes=int(data.get("min_html_bytes", args.min_html_bytes)),
        wait_selector=data.get("wait_selector") or args.wait_selector,
        headless=bool(data.get("headless", not args.headful)),
        sandbox=not bool(data.get("no_sandbox", args.no_sandbox)),
        browser_executable_path=data.get("browser_executable_path") or args.browser_executable_path,
        user_data_dir=data.get("user_data_dir") or args.user_data_dir,
        proxy_server=data.get("proxy_server") or args.proxy_server,
        use_default_browser_flags=bool(use_default_browser_flags),
        browser_args=browser_args,
        save_html=save_html,
        output_format=str(data.get("output_format") or args.output_format),
        embed_html=bool(data.get("embed_html", args.embed_html)),
    )


def _print_payload(settings: FetchSettings, result: FetchResult, html: str) -> None:
    embedded_html = html if settings.embed_html else None
    if settings.output_format == "openclaw":
        payload = _to_openclaw_payload(result, embedded_html)
    else:
        payload = asdict(result)
        if embedded_html is not None:
            payload["html"] = embedded_html
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    """Запускает CLI-сценарий и возвращает код завершения процесса."""
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not args.verbose:
        logging.getLogger("nodriver").setLevel(logging.WARNING)
        logging.getLogger("websockets").setLevel(logging.WARNING)

    try:
        settings = _build_settings(args)
    except Exception as exc:
        json.dump({"status": "error", "error": str(exc)}, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 1

    LOGGER.info("Запрос %s", settings.url)
    result, html = uc.loop().run_until_complete(fetch_html(settings))
    _print_payload(settings, result, html)

    if result.ok:
        return 0
    if result.blocked or result.challenge_detected:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
