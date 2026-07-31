"""Прямой HTTP-клиент к Mercari search API (Уровень B).

Заменяет Playwright/BrowserManager. Экспериментально подтверждено:
- cookies не нужны (Cloudflare на текущей нагрузке пускает обычный aiohttp);
- до 50 одновременных запросов с одного IP работают без throttling;
- потолок ~60 RPS. Держим max_concurrency=10 + request_delay как 5× margin.

Архитектура готова к подключению cookie-manager'а (свойство `cookies`),
если Cloudflare начнёт требовать __cf_bm при росте нагрузки.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from mercari.conditions import SearchCondition
from mercari.dpop import DpopSigner
from mercari.parser import parse_items
from models.item import Item

logger = logging.getLogger(__name__)

SEARCH_API_URL = "https://api.mercari.jp/v2/entities:search"

# Заголовки зафиксированы по реальному запросу браузера — они важны серверу
# для корректного ответа, но не для авторизации (DPoP — единственная защита).
COMMON_HEADERS: dict[str, str] = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en",
    "content-type": "application/json",
    "origin": "https://jp.mercari.com",
    "referer": "https://jp.mercari.com/",
    "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "x-country-code": "RU",
    "x-platform": "web",
}

MAX_RETRIES = 2
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_CAP_SECONDS = 60.0
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class MercariClientError(RuntimeError):
    """4xx от Mercari (кроме 429) — повторять бессмысленно."""


class MercariClient:
    """Асинхронный HTTP-клиент к Mercari search API.

    Один экземпляр = одна aiohttp.ClientSession (keep-alive, переиспользование
    TCP-соединений). Потокобезопасен в рамках asyncio.
    """

    def __init__(
        self,
        dpop: DpopSigner | None = None,
        *,
        max_concurrency: int = 10,
        request_delay: float = 0.0,
        proxy: str | None = None,
        cookies: dict[str, str] | None = None,
    ) -> None:
        # `dpop` опционален: основной путь (watcher) передаёт per-user signer
        # явно в search(). Дефолт нужен только для не-user контекстов (тесты,
        # админ-запросы), где личность фиксирована на старте.
        self._dpop = dpop
        self._proxy = proxy
        self._cookies = cookies
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._request_delay = request_delay
        self._session: aiohttp.ClientSession | None = None

    @property
    def device_uuid(self) -> str | None:
        # None, если дефолтная личность не задана — caller должен передать
        # signer в search() явно.
        return self._dpop.device_uuid if self._dpop is not None else None

    async def __aenter__(self) -> "MercariClient":
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def start(self) -> None:
        if self._session is not None:
            logger.debug("MercariClient.start() called but session already exists — skipping")
            return
        # limit_per_host=0 → без ограничений на соединения к api.mercari.jp;
        # реальный потолок задаётся semaphore'ом.
        connector = aiohttp.TCPConnector(limit=0)
        self._session = aiohttp.ClientSession(
            timeout=REQUEST_TIMEOUT,
            connector=connector,
            cookies=self._cookies,
        )
        logger.info("=" * 50)
        logger.info("🌐 MERCARI CLIENT STARTED")
        logger.info("   Max concurrency: %s (semaphore slots)", self._semaphore._value)
        logger.info("   Request delay:   %s seconds (self-throttle)", self._request_delay)
        logger.info("   Proxy:           %s", self._proxy or "none (direct connection)")
        logger.info("   Cookies:         %s", "provided" if self._cookies else "none")
        logger.info("   Default device:  %s", self._dpop.device_uuid if self._dpop else "(per-user signers)")
        logger.info("   API endpoint:    %s", SEARCH_API_URL)
        logger.info("=" * 50)

    async def aclose(self) -> None:
        if self._session is not None:
            logger.info("⏳ Closing Mercari client session...")
            await self._session.close()
            self._session = None
            logger.info("=" * 50)
            logger.info("🌐 MERCARI CLIENT CLOSED")
            logger.info("   Session closed, connections released")
            logger.info("=" * 50)
        else:
            logger.debug("MercariClient.aclose() called but session was already closed")

    async def search(
        self,
        condition: SearchCondition,
        *,
        page_size: int = 30,
        dpop: DpopSigner | None = None,
    ) -> list[Item]:
        """Выполняет поиск по условию. Возвращает распарсенные товары.

        Потокобезопасность: semaphore ограничивает одновременные запросы.
        Ретраи: только на 429/5xx (временные сбои). На 4xx — сразу raise.

        `dpop`: per-user DPoP-подписчик. Если передан — запрос уходит от
        имени этого пользователя (его device_uuid в payload и в JWT).
        Если нет — используется дефолтный signer клиента (`self._dpop`).
        Дефолтный signer может быть None — тогда поднимается RuntimeError:
        ни per-user, ни fallback-личности не задано.
        """
        signer = dpop if dpop is not None else self._dpop
        if signer is None:
            raise RuntimeError(
                "No DPoP signer: pass per-user signer via `dpop=` or configure "
                "a default signer on MercariClient."
            )
        async with self._semaphore:
            try:
                return await self._search_with_retries(condition, page_size, signer)
            finally:
                # Мягкий self-throttling: пауза после освобождения слота, чтобы
                # не держать сервер постоянным потоком на пределе лимита.
                if self._request_delay > 0:
                    await asyncio.sleep(self._request_delay)

    async def _search_with_retries(
        self, condition: SearchCondition, page_size: int, signer: DpopSigner,
    ) -> list[Item]:
        payload = condition.to_payload(signer.device_uuid, page_size=page_size)
        last_exc: Exception | None = None

        # Log search condition details
        keyword = condition.keyword or "(no keyword)"
        brand = condition.brand_id or "(any brand)"
        category = condition.category_id or "(any category)"
        price_range = f"{condition.price_min}–{condition.price_max}" if condition.price_min or condition.price_max else "any"
        logger.info(
            "🔍 Search request: keyword='%s', brand=%s, category=%s, price=%s, sort=%s, order=%s, page_size=%s",
            keyword, brand, category, price_range, condition.sort, condition.order, page_size,
        )

        for attempt in range(1, MAX_RETRIES + 2):  # 1 попытка + MAX_RETRIES ретраев
            dpop_header = signer.sign("POST", SEARCH_API_URL)
            headers = {**COMMON_HEADERS, "dpop": dpop_header}
            try:
                logger.debug("Attempt %s/%s: sending request to Mercari API", attempt, MAX_RETRIES + 1)
                result = await self._do_request(headers, payload)
                logger.info("✅ Search completed on attempt %s/%s", attempt, MAX_RETRIES + 1)
                return result
            except _Retryable as exc:
                last_exc = exc
                if attempt > MAX_RETRIES:
                    logger.error("❌ All %s retry attempts exhausted — giving up", MAX_RETRIES)
                    break
                delay = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                logger.warning(
                    "⚠️  Retryable error (attempt %s/%s): %s — retrying in %.1fs",
                    attempt, MAX_RETRIES + 1, exc, delay,
                )
                await asyncio.sleep(delay)
            except MercariClientError:
                logger.error("❌ Non-retryable Mercari error (4xx) — aborting search")
                raise  # 4xx не повторяем
        raise RuntimeError("Mercari search failed after retries") from last_exc

    async def _do_request(
        self, headers: dict[str, str], payload: dict[str, Any]
    ) -> list[Item]:
        if self._session is None:
            raise RuntimeError("MercariClient is not started; call start() first")
        try:
            logger.debug("📡 POST %s (payload keys: %s)", SEARCH_API_URL, list(payload.keys()))
            async with self._session.post(
                SEARCH_API_URL,
                headers=headers,
                json=payload,
                proxy=self._proxy,
            ) as response:
                logger.debug("↩ HTTP %s (content-type: %s)", response.status, response.content_type)
                if response.status == 200:
                    data = await response.json()
                    items = parse_items(data)
                    logger.info("✅ Mercari search returned %s items (HTTP 200)", len(items))
                    return items
                body = await response.text()
                logger.warning("⚠️  HTTP %s from Mercari API: %s", response.status, body[:200])
                # 429 / 5xx — повторяем, прочие 4xx — нет смысла.
                if response.status == 429 or response.status >= 500:
                    raise _Retryable(f"HTTP {response.status}: {body[:200]}")
                raise MercariClientError(
                    f"HTTP {response.status}: {body[:200]}"
                )
        except aiohttp.ClientError as exc:
            logger.warning("⚠️  aiohttp network error: %s", exc)
            # Сетевые сбои тоже ретраим — они часто мимолётны.
            raise _Retryable(f"aiohttp error: {exc}") from exc
        except asyncio.TimeoutError as exc:
            logger.warning("⚠️  Request timeout (%ss) — will retry", REQUEST_TIMEOUT.total)
            raise _Retryable("request timeout") from exc


class _Retryable(Exception):
    """Внутренний маркер: ошибку стоит повторить."""
