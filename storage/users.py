import time

from storage.connection import DatabaseConnection


SUPPORTED_LANGUAGES = frozenset({"ru", "en"})
DEFAULT_LANGUAGE = "ru"


class UserStorage:
    """Stores the language selected by each Telegram chat."""

    def __init__(self, db: DatabaseConnection) -> None:
        self._db = db

    async def get_language(self, chat_id: str) -> str | None:
        cursor = await self._db.conn.execute(
            "SELECT language FROM users WHERE chat_id = ?", (chat_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def set_language(self, chat_id: str, language: str) -> None:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        now = int(time.time())
        async with self._db.transaction() as conn:
            await conn.execute(
                "INSERT INTO users (chat_id, language, created_at, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(chat_id) DO UPDATE SET language = excluded.language, "
                "updated_at = excluded.updated_at",
                (chat_id, language, now, now),
            )

    async def remove_user(self, chat_id: str) -> None:
        async with self._db.transaction() as conn:
            await conn.execute(
                "DELETE FROM users WHERE chat_id = ?", (chat_id,),
            )

    async def count(self) -> int:
        cursor = await self._db.conn.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_all_chat_ids(self) -> set[str]:
        rows = await self._db.conn.execute_fetchall("SELECT chat_id FROM users")
        return {row[0] for row in rows}

    async def get_state(self, key: str) -> str | None:
        cursor = await self._db.conn.execute(
            "SELECT value FROM bot_state WHERE key = ?", (key,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def set_state(self, key: str, value: str) -> None:
        async with self._db.transaction() as conn:
            await conn.execute(
                "INSERT INTO bot_state (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
