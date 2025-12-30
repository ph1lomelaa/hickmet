#!/usr/bin/env python3
"""
Тестовый скрипт для проверки поиска дат марта
"""
import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bull_project.bull_bot.core.smart_search import get_packages_by_date


async def test_date_search():
    """Тестируем поиск даты 07.03"""

    print("=" * 60)
    print("ТЕСТ ПОИСКА ДАТЫ 07.03")
    print("=" * 60)

    # Тестируем разные форматы
    test_dates = ["07.03", "7.03", "07.3", "7.3"]

    for date in test_dates:
        print(f"\n{'='*60}")
        print(f"Тестируем дату: {date}")
        print(f"{'='*60}\n")

        result = await get_packages_by_date(date, force=True)

        print(f"\n{'='*60}")
        print(f"РЕЗУЛЬТАТ для {date}:")
        print(f"  found: {result.get('found')}")
        print(f"  data_count: {len(result.get('data', []))}")
        if result.get('error'):
            print(f"  error: {result.get('error')}")
        if result.get('data'):
            print(f"\n  Найденные пакеты:")
            for pkg in result['data'][:5]:  # Показываем первые 5
                print(f"    - {pkg['n']} | {pkg['s']}")
        print(f"{'='*60}\n")

        # Проверяем только первый вариант, так как остальные используют кеш
        if date == "07.03":
            break


if __name__ == "__main__":
    asyncio.run(test_date_search())
