import asyncio
import logging
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

PLATEGA_API_URL = "https://app.platega.io"
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)
MAX_RETRIES = 2

METHOD_SBP_QR = 2

STATUS_PENDING = "PENDING"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_CANCELED = "CANCELED"
STATUS_CHARGEBACKED = "CHARGEBACKED"


@dataclass(slots=True)
class PlategaTransaction:
    transaction_id: str
    status: str
    amount: float
    currency: str
    redirect_url: str
    description: str | None
    created_at: str
    payload: str | None


class PlategaClient:

    def __init__(self, merchant_id: str, secret: str) -> None:
        self._merchant_id = merchant_id
        self._secret = secret
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT)
        logger.info("✅ Platega HTTP client started")

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
            logger.info("✅ Platega HTTP client closed")

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("PlategaClient is not started")
        return self._session

    @staticmethod
    def _parse_details(raw: str | dict) -> tuple[float, str]:
        """Parse paymentDetails which may be '108.5 RUB' (str) or {'amount': 108.5, 'currency': 'RUB'} (dict)."""
        if isinstance(raw, dict):
            return float(raw.get("amount", 0)), raw.get("currency", "")
        parts = raw.strip().split()
        if len(parts) >= 2:
            return float(parts[0]), parts[1]
        return 0.0, ""

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-MerchantId": self._merchant_id,
            "X-Secret": self._secret,
        }

    async def create_payment(
        self,
        amount: float,
        currency: str = "RUB",
        description: str = "",
        payload: str | None = None,
    ) -> PlategaTransaction | None:
        body: dict = {
            "paymentMethod": METHOD_SBP_QR,
            "paymentDetails": {
                "amount": float(amount),
                "currency": currency,
            },
        }
        if description:
            body["description"] = description
        if payload:
            body["payload"] = payload

        url = f"{PLATEGA_API_URL}/transaction/process"
        logger.debug("📤 Platega POST /transaction/process (amount=%s %s)", amount, currency)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with self.session.post(url, headers=self._headers(), json=body) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        amount, currency_val = self._parse_details(data.get("paymentDetails", {}))
                        txn = PlategaTransaction(
                            transaction_id=data.get("transactionId", ""),
                            status=data.get("status", ""),
                            amount=amount,
                            currency=currency_val,
                            redirect_url=data.get("redirect", ""),
                            description=data.get("description"),
                            created_at=data.get("createdAt", ""),
                            payload=data.get("payload"),
                        )
                        return txn
                    logger.error(
                        "❌ Platega createPayment error: HTTP %s — %s",
                        resp.status,
                        data.get("message", str(data)),
                    )
                    return None
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                logger.error("❌ Platega request failed (attempt %s/%s): %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1)
        return None

    async def get_payment_status(self, transaction_id: str) -> PlategaTransaction | None:
        url = f"{PLATEGA_API_URL}/transaction/{transaction_id}"
        logger.debug("📤 Platega GET /transaction/%s", transaction_id)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with self.session.get(url, headers=self._headers()) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        amount, currency_val = self._parse_details(data.get("paymentDetails", {}))
                        return PlategaTransaction(
                            transaction_id=data.get("transactionId") or data.get("id", ""),
                            status=data.get("status", ""),
                            amount=amount,
                            currency=currency_val,
                            redirect_url=data.get("redirect", ""),
                            description=data.get("description"),
                            created_at=data.get("createdAt", ""),
                            payload=data.get("payload"),
                        )
                    logger.error(
                        "❌ Platega getPaymentStatus error: HTTP %s — %s",
                        resp.status,
                        data.get("message", str(data)),
                    )
                    return None
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                logger.error("❌ Platega request failed (attempt %s/%s): %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1)
        return None

    async def cancel_transaction(self, transaction_id: str) -> bool:
        url = f"{PLATEGA_API_URL}/transaction/{transaction_id}/cancel"
        logger.debug("📤 Platega POST /transaction/%s/cancel", transaction_id)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                headers = {**self._headers(), "Accept": "text/plain, application/json"}
                async with self.session.post(url, headers=headers) as resp:
                    if resp.status == 200:
                        logger.info("🗑️ Platega transaction #%s cancelled", transaction_id)
                        return True
                    try:
                        data = await resp.json()
                    except Exception:
                        data = {"message": await resp.text()}
                    logger.error(
                        "❌ Platega cancelTransaction error: HTTP %s — %s",
                        resp.status,
                        data.get("message", str(data)),
                    )
                    return False
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                logger.error("❌ Platega request failed (attempt %s/%s): %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1)
        return False
