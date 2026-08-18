"""Standalone proof-of-concept: прямой HTTP-клиент к Mercari API (Уровень B).

Запуск:
    python test_api.py

Проверяет три вещи:
1. Один запрос → возвращает товары (собственный DPoP-ключ принимается).
2. Параллельный батч из 10 запросов → все успешны, выводит тайминги.
3. Парсинг URL → корректное тело запроса.

Если всё работает на вашей машине — ядро Уровня B готово, можно интегрировать
в app.py (Этап 2).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid

# Чтобы скрипт запускался из корня проекта без установки пакета.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mercari.client import MercariClient
from mercari.conditions import SearchCondition, parse_search_url
from mercari.dpop import DpopSigner

# Тестовый URL — тот же, что использовался в экспериментах (Nintendo Switch).
TEST_URL = "https://jp.mercari.com/en/search?brand_id=7572&sort=created_time&order=desc"

# Один device_uuid на запуск. В реальном приложении хранится в .env.
DEVICE_UUID = uuid.uuid4().hex


def _print_item(item, idx: int) -> None:
    title = item.title[:50] + ("…" if len(item.title) > 50 else "")
    print(f"  {idx:2}. ¥{item.price:>7,}  {item.id}  {title}")


async def run_single_request(client: MercariClient) -> None:
    print("\n" + "=" * 70)
    print("ТЕСТ 1: один запрос к Mercari API")
    print("=" * 70)
    condition = parse_search_url(TEST_URL)
    print(f"URL       : {TEST_URL}")
    print(f"Condition : brand_id={condition.brand_id}, sort={condition.sort}")
    print(f"device_uuid: {client.device_uuid}")

    t0 = time.time()
    items = await client.search(condition, page_size=5)
    dt = time.time() - t0
    print(f"\nПолучено {len(items)} товаров за {dt:.2f}с:\n")
    for i, item in enumerate(items, 1):
        _print_item(item, i)


async def run_parallel_batch(client: MercariClient) -> None:
    print("\n" + "=" * 70)
    print("ТЕСТ 2: 10 запросов параллельно (asyncio.gather)")
    print("=" * 70)
    condition = parse_search_url(TEST_URL)
    t0 = time.time()
    results = await asyncio.gather(
        *[client.search(condition, page_size=5) for _ in range(10)],
        return_exceptions=True,
    )
    dt = time.time() - t0
    ok = sum(1 for r in results if not isinstance(r, Exception))
    print(f"Успешно: {ok}/10 за {dt:.2f}с (эффективный RPS: {10/dt:.1f})")
    for i, r in enumerate(results, 1):
        if isinstance(r, Exception):
            print(f"  #{i}: ОШИБКА {r}")
    if ok == 10:
        print("Все 10 батчей прошли без ошибок.")


async def run_url_parsing() -> None:
    print("\n" + "=" * 70)
    print("ТЕСТ 3: парсинг URL → SearchCondition")
    print("=" * 70)
    cases = [
        TEST_URL,
        "https://jp.mercari.com/en/search?category_id=7021",
        "https://jp.mercari.com/en/search?keyword=Nintendo%20Switch&price_min=1000&price_max=5000",
        "https://jp.mercari.com/search?brand_id=7572&sort=price&order=asc",
    ]
    for url in cases:
        c = parse_search_url(url)
        print(f"  {url}")
        print(
            f"    → brand={c.brand_id} cat={c.category_id} kw='{c.keyword}' "
            f"sort={c.sort} price={c.price_min}-{c.price_max}"
        )


async def main() -> None:
    print("=" * 70)
    print("MERCARI API — LEVEL B PROOF-OF-CONCEPT")
    print("=" * 70)
    print(f"Эндпоинт: https://api.mercari.jp/v2/entities:search")
    print(f"Без Playwright, без cookies, прямой aiohttp + DPoP")

    # Сначала проверяем парсинг (без сети).
    await run_url_parsing()

    # Затем — реальные запросы.
    dpop = DpopSigner(DEVICE_UUID)
    async with MercariClient(dpop, max_concurrency=5, request_delay=0.1) as client:
        await run_single_request(client)
        await run_parallel_batch(client)

    print("\n" + "=" * 70)
    print("✅ Ядро Уровня B работает. Готово к интеграции в app.py (Этап 2).")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
