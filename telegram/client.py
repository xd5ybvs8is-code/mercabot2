import asyncio
import json
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=15)
MAX_RETRIES = 2


class TelegramRateLimitError(Exception):
    """Raised on HTTP 429. Carries retry_after (seconds) requested by Telegram."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"Telegram rate limited (retry_after={retry_after}s)")
        self.retry_after = retry_after


class TelegramPermanentError(Exception):
    """Raised on permanent Telegram errors (chat not found, blocked, etc.).

    These should never be retried — the chat/user is gone forever.
    """

    def __init__(self, status: int, description: str, error_code: int | None = None) -> None:
        super().__init__(f"Telegram permanent error {status}: {description}")
        self.status = status
        self.description = description
        self.error_code = error_code


_PERMANENT_DESCRIPTIONS: set[str] = {
    "chat not found",
    "user_id is invalid",
    "bot was blocked by the user",
    "user is deactivated",
    "group chat was upgraded",
    "bot was kicked from the group chat",
    "bot was kicked from the supergroup chat",
    "bot was kicked from the channel chat",
    "group chat is deactivated",
    "group is deactivated",
    "chat write access is forbidden",
    "have no rights to send a message",
}


def _is_permanent_error(body: str) -> bool:
    """Check whether a Telegram error response indicates a permanent failure."""
    try:
        data = json.loads(body)
        desc = data.get("description", "")
        if isinstance(desc, str):
            desc_lower = desc.strip().lower()
            for pattern in _PERMANENT_DESCRIPTIONS:
                if pattern in desc_lower:
                    return True
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return False


def _parse_error_body(body: str) -> tuple[str, int | None]:
    """Extract (description, error_code) from a Telegram error JSON."""
    try:
        data = json.loads(body)
        return (
            data.get("description", body),
            data.get("error_code"),
        )
    except (json.JSONDecodeError, TypeError, AttributeError):
        return (body, None)


def _api_url(token: str, method: str) -> str:
    return TELEGRAM_API_URL.format(token=token, method=method)


class TelegramClient:
    """Low-level Telegram Bot API client."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        logger.debug("TelegramClient.start(): creating HTTP session")
        self._session = aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT)
        logger.info("✅ Telegram HTTP client started")

    async def close(self) -> None:
        if self._session is not None:
            logger.debug("TelegramClient.close(): closing HTTP session")
            await self._session.close()
            self._session = None
            logger.info("✅ Telegram HTTP client closed")

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("TelegramClient is not started")
        return self._session

    async def call_api(self, method: str, payload: dict[str, Any]) -> bool:
        """POST-запрос (sendMessage и т.д.). Возвращает True при 200.

        На HTTP 429 бросает TelegramRateLimitError (без ретраев внутри клиента —
        обработкой дросселя занимается MessageSender).
        """
        url = _api_url(self._token, method)
        logger.debug("📤 Telegram POST %s (payload keys: %s)", method, list(payload.keys()))
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with self.session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if not data.get("ok"):
                            logger.error(
                                "❌ Telegram %s API error: %s (error_code=%s)",
                                method,
                                data.get("description", "unknown"),
                                data.get("error_code", "N/A"),
                            )
                            return False
                        logger.debug("✅ Telegram %s: HTTP 200", method)
                        return True
                    if response.status == 429:
                        retry_after = self._parse_retry_after(await response.text())
                        logger.warning(
                            "⚠️ Telegram 429 rate limit on %s (retry_after=%ss)",
                            method, retry_after,
                        )
                        raise TelegramRateLimitError(retry_after)
                    body = await response.text()
                    if _is_permanent_error(body):
                        desc, code = _parse_error_body(body)
                        raise TelegramPermanentError(response.status, desc, code)
                    logger.error(
                        "❌ Telegram API error (attempt %s/%s): %s %s",
                        attempt, MAX_RETRIES, response.status, body,
                    )
            except TelegramRateLimitError:
                raise
            except TelegramPermanentError:
                raise
            except (asyncio.TimeoutError, aiohttp.ClientError, json.JSONDecodeError, TypeError, ValueError) as exc:
                logger.error(
                    "❌ Telegram request failed (attempt %s/%s): %s",
                    attempt, MAX_RETRIES, exc,
                )
            if attempt < MAX_RETRIES:
                logger.debug("⏳ Retrying Telegram %s in 1s (attempt %s/%s)...", method, attempt, MAX_RETRIES)
                await asyncio.sleep(1)
        return False

    @staticmethod
    def _parse_retry_after(body: str) -> float:
        """Извлекает retry_after из JSON-ответа Telegram. Дефолт 1.0с."""
        try:
            data = json.loads(body)
            value = data.get("parameters", {}).get("retry_after")
            if value is not None:
                return float(value)
        except (json.JSONDecodeError, TypeError, AttributeError, ValueError):
            pass
        return 1.0

    async def call_api_json(self, method: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST-запрос с возвратом JSON-ответа.

        Возвращает распарсенный JSON при 200, None при ошибке.
        На HTTP 429 бросает TelegramRateLimitError.
        Используется для inline-клавиатур и других случаев, где нужен
        message_id из ответа Telegram.
        """
        url = _api_url(self._token, method)
        logger.debug("📤 Telegram POST %s (payload keys: %s)", method, list(payload.keys()))
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with self.session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if not data.get("ok"):
                            logger.error(
                                "❌ Telegram %s API error: %s (error_code=%s)",
                                method,
                                data.get("description", "unknown"),
                                data.get("error_code", "N/A"),
                            )
                            return None
                        logger.debug("✅ Telegram %s: HTTP 200", method)
                        return data
                    if response.status == 429:
                        retry_after = self._parse_retry_after(await response.text())
                        logger.warning(
                            "⚠️ Telegram 429 rate limit on %s (retry_after=%ss)",
                            method, retry_after,
                        )
                        raise TelegramRateLimitError(retry_after)
                    body = await response.text()
                    if _is_permanent_error(body):
                        desc, code = _parse_error_body(body)
                        raise TelegramPermanentError(response.status, desc, code)
                    logger.error(
                        "❌ Telegram API error (attempt %s/%s): %s %s",
                        attempt, MAX_RETRIES, response.status, body,
                    )
                    if attempt < MAX_RETRIES:
                        continue
                    return None
            except TelegramRateLimitError:
                raise
            except TelegramPermanentError:
                raise
            except (asyncio.TimeoutError, aiohttp.ClientError, json.JSONDecodeError, TypeError, ValueError) as exc:
                logger.error(
                    "❌ Telegram request failed (attempt %s/%s): %s",
                    attempt, MAX_RETRIES, exc,
                )
            if attempt < MAX_RETRIES:
                logger.debug("⏳ Retrying Telegram %s in 1s (attempt %s/%s)...", method, attempt, MAX_RETRIES)
                await asyncio.sleep(1)
        return None

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None, show_alert: bool = False) -> bool:
        """Answer a callback query (inline keyboard press)."""
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert
        result = await self.call_api_json("answerCallbackQuery", payload)
        return result is not None

    async def edit_message_text(
        self, chat_id: str, message_id: int, text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> bool:
        """Edit a previously sent message."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = await self.call_api_json("editMessageText", payload)
        return result is not None

    async def call_api_raw(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """GET-запрос (getUpdates). Возвращает JSON или None."""
        url = _api_url(self._token, method)
        logger.debug("📤 Telegram GET %s (params: %s)", method, params)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        update_count = len(data.get("result", []))
                        logger.debug("✅ Telegram %s: HTTP 200 (%s updates)", method, update_count)
                        return data
                    log_level = logger.warning if attempt < MAX_RETRIES else logger.error
                    log_level(
                        "⚠️ Telegram API error %s (attempt %s/%s): %s",
                        method, attempt, MAX_RETRIES, response.status,
                    )
            except (asyncio.TimeoutError, aiohttp.ClientError, json.JSONDecodeError, TypeError, ValueError) as exc:
                log_level = logger.warning if attempt < MAX_RETRIES else logger.error
                log_level(
                    "⚠️ Telegram request failed %s (attempt %s/%s): %s",
                    method, attempt, MAX_RETRIES, exc,
                )
            if attempt < MAX_RETRIES:
                logger.debug("⏳ Retrying Telegram %s in 1s...", method)
                await asyncio.sleep(1)
        return None
