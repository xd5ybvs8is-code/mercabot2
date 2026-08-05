import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

CRYPTOBOT_API_URL = "https://pay.crypt.bot/api"
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=15)
MAX_RETRIES = 2


@dataclass(slots=True)
class CryptoInvoice:
    invoice_id: int
    status: str
    hash: str
    asset: str
    amount: str
    pay_url: str
    bot_invoice_url: str
    description: str | None
    created_at: str
    paid_at: str | None
    payload: str | None


class CryptoPayClient:

    def __init__(self, api_token: str) -> None:
        self._api_token = api_token
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT)
        logger.info("✅ CryptoBot HTTP client started")

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
            logger.info("✅ CryptoBot HTTP client closed")

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("CryptoPayClient is not started")
        return self._session

    def _headers(self) -> dict[str, str]:
        return {
            "Crypto-Pay-API-Token": self._api_token,
            "Content-Type": "application/json",
        }

    async def create_invoice(
        self,
        amount: str,
        asset: str = "USDT",
        currency_type: str = "fiat",
        fiat: str = "RUB",
        description: str = "",
        payload: str | None = None,
    ) -> CryptoInvoice | None:
        body: dict[str, Any] = {
            "amount": amount,
            "currency_type": currency_type,
            "asset": asset,
        }
        if currency_type == "fiat":
            body["fiat"] = fiat
        if description:
            body["description"] = description
        if payload:
            body["payload"] = payload

        url = f"{CRYPTOBOT_API_URL}/createInvoice"
        logger.debug("📤 CryptoBot POST createInvoice (amount=%s %s)", amount, asset)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with self.session.post(url, headers=self._headers(), json=body) as resp:
                    data = await resp.json()
                    if resp.status == 200 and data.get("ok"):
                        invoice_data = data.get("result", {})
                        invoice = CryptoInvoice(
                            invoice_id=invoice_data.get("invoice_id", 0),
                            status=invoice_data.get("status", ""),
                            hash=invoice_data.get("hash", ""),
                            asset=invoice_data.get("asset", ""),
                            amount=invoice_data.get("amount", ""),
                            pay_url=invoice_data.get("pay_url", ""),
                            bot_invoice_url=invoice_data.get("bot_invoice_url", ""),
                            description=invoice_data.get("description"),
                            created_at=invoice_data.get("created_at", ""),
                            paid_at=invoice_data.get("paid_at"),
                            payload=invoice_data.get("payload"),
                        )
                        logger.info("✅ CryptoBot invoice #%s created (status=%s)", invoice.invoice_id, invoice.status)
                        return invoice
                    logger.error(
                        "❌ CryptoBot createInvoice error: %s (code=%s)",
                        data.get("error", {}).get("name"),
                        data.get("error", {}).get("code"),
                    )
                    return None
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                logger.error("❌ CryptoBot request failed (attempt %s/%s): %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1)
        return None

    async def get_invoices(self, invoice_ids: list[int]) -> list[CryptoInvoice]:
        url = f"{CRYPTOBOT_API_URL}/getInvoices"
        params: dict[str, Any] = {
            "invoice_ids": ",".join(str(i) for i in invoice_ids),
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with self.session.get(url, headers=self._headers(), params=params) as resp:
                    data = await resp.json()
                    if resp.status == 200 and data.get("ok"):
                        results = data.get("result", {}).get("items", [])
                        invoices: list[CryptoInvoice] = []
                        for inv in results:
                            invoices.append(CryptoInvoice(
                                invoice_id=inv.get("invoice_id", 0),
                                status=inv.get("status", ""),
                                hash=inv.get("hash", ""),
                                asset=inv.get("asset", ""),
                                amount=inv.get("amount", ""),
                                pay_url=inv.get("pay_url", ""),
                                bot_invoice_url=inv.get("bot_invoice_url", ""),
                                description=inv.get("description"),
                                created_at=inv.get("created_at", ""),
                                paid_at=inv.get("paid_at"),
                                payload=inv.get("payload"),
                            ))
                        return invoices
                    logger.error(
                        "❌ CryptoBot getInvoices error: %s",
                        data.get("error", {}).get("name"),
                    )
                    return []
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                logger.error("❌ CryptoBot request failed (attempt %s/%s): %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1)
        return []

    async def get_balance(self) -> list[dict[str, Any]]:
        url = f"{CRYPTOBOT_API_URL}/getBalance"

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with self.session.get(url, headers=self._headers()) as resp:
                    data = await resp.json()
                    if resp.status == 200 and data.get("ok"):
                        return data.get("result", [])
                    logger.error(
                        "❌ CryptoBot getBalance error: %s",
                        data.get("error", {}).get("name"),
                    )
                    return []
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                logger.error("❌ CryptoBot request failed (attempt %s/%s): %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1)
        return []
