"""Per-user device-личности для Mercari DPoP.

Раньше у всего процесса был один `device_uuid` (и одна EC P-256 пара) —
все запросы от имени всех пользователей бота выглядели для Mercari как
одно устройство. Это иRate-limit'ы, и риск блокировки распространялись на
всех сразу, а антифрод мог увидеть аномалию.

Теперь каждый `user_chat_id` получает собственные:
- `device_uuid` — персистится в `user_devices` таблице;
- EC P-256 пару — генерируется в `DpopSigner` и живёт только в памяти
  (сервер Mercari не привязывает ключ к UUID — см. mercari/dpop.py).

`DeviceRegistry` — тонкий слой над БД: лениво подгружает/создаёт signer'ов
и кэширует их в памяти процесса. Кэш неограничен: масштаб <= ~50 юзеров,
сотни EC-ключей в памяти ничтожны. Для бóльших нагрузок нужен LRU.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid as uuidlib

from mercari.dpop import DpopSigner
from storage.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class DeviceRegistry:
    """Резолвит per-user `DpopSigner` с ленивой инициализацией и кэшем в памяти.

    Потокобезопасность: чек→создание защищены локом, чтобы при первом
    запросе пользователя в параллельном `asyncio.gather` не создалось
    две записи в БД (UNIQUE тоже спасает, но лок дешевле INSERT OR IGNORE).
    """

    def __init__(self, db: DatabaseConnection) -> None:
        self._db = db
        self._cache: dict[str, DpopSigner] = {}
        # Сериализует путь «нет в кэше → чек БД → возможный INSERT».
        self._lock = asyncio.Lock()

    async def get_signer(self, user_chat_id: str) -> DpopSigner:
        """Возвращает `DpopSigner` для пользователя (из кэша или БД).

        При первом обращении генерирует новый `device_uuid`, сохраняет его
        в `user_devices` и создаёт signer. Последующие вызовы берут signer
        из in-memory кэша (EC-ключ в БД не хранится — только UUID).
        """
        cached = self._cache.get(user_chat_id)
        if cached is not None:
            return cached

        async with self._lock:
            # Повторная проверка под локом: другая корутина могла уже
            # заполнить кэш, пока мы ждали.
            cached = self._cache.get(user_chat_id)
            if cached is not None:
                return cached

            device_uuid, is_new = await self._load_or_create(user_chat_id)
            signer = DpopSigner(device_uuid)
            self._cache[user_chat_id] = signer
            logger.info(
                "🔑 Device signer ready for user %s (device_uuid=%s, %s)",
                user_chat_id, device_uuid, "newly created" if is_new else "loaded from db",
            )
            return signer

    async def _load_or_create(self, user_chat_id: str) -> tuple[str, bool]:
        """SELECT существующего UUID; если нет — генерация + INSERT.

        Возвращает `(device_uuid, is_new)`. INSERT обёрнут в `transaction()`
        для атомарности и совместимости с общим `_tx_lock` соединения.
        """
        cursor = await self._db.conn.execute(
            "SELECT device_uuid FROM user_devices WHERE user_chat_id = ?",
            (user_chat_id,),
        )
        row = await cursor.fetchone()
        if row is not None:
            logger.debug("📋 Loaded existing device_uuid for user %s", user_chat_id)
            return row[0], False

        new_uuid = uuidlib.uuid4().hex
        async with self._db.transaction() as conn:
            # INSERT OR IGNORE — защита на уровне БД от гонки/дубликата,
            # даже если лок по какой-то причине не сработал.
            await conn.execute(
                "INSERT OR IGNORE INTO user_devices (user_chat_id, device_uuid, created_at) "
                "VALUES (?, ?, ?)",
                (user_chat_id, new_uuid, int(time.time())),
            )
        logger.info("✨ Generated new device_uuid for user %s", user_chat_id)
        return new_uuid, True
