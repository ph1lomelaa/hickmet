#!/usr/bin/env python3
"""
Показывает содержимое мартовского листа для отладки
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bull_project.bull_bot.core.google_sheets.client import (
    get_accessible_tables,
    get_sheet_client
)

def inspect_march_sheet():
    """Смотрим что внутри листа 07.03"""

    print("=" * 80)
    print("ИНСПЕКЦИЯ МАРТОВСКОГО ЛИСТА")
    print("=" * 80)

    # Получаем таблицы
    tables = get_accessible_tables()
    march_table = None
    march_id = None

    for name, tid in tables.items():
        if "MARCH" in name or "RAMADAN" in name:
            march_table = name
            march_id = tid
            break

    if not march_table:
        print("❌ Таблица MARCH/RAMADAN не найдена!")
        return

    print(f"✅ Найдена таблица: {march_table}")
    print(f"   ID: {march_id}\n")

    # Открываем таблицу
    gc = get_sheet_client()
    spreadsheet = gc.open_by_key(march_id)

    # Ищем лист 07.03
    target_sheet = None
    for ws in spreadsheet.worksheets():
        if ws.title.startswith("07.03"):
            target_sheet = ws
            break

    if not target_sheet:
        print("❌ Лист 07.03 не найден!")
        print("Доступные листы:")
        for ws in spreadsheet.worksheets():
            print(f"  - {ws.title}")
        return

    print(f"✅ Найден лист: {target_sheet.title}\n")
    print("=" * 80)
    print("СОДЕРЖИМОЕ ПЕРВЫХ 50 СТРОК (колонки A-B):")
    print("=" * 80)

    # Читаем первые 50 строк, колонки A-B
    data = target_sheet.get('A1:B50')

    for idx, row in enumerate(data, start=1):
        if not row:
            continue
        row_text = " | ".join(row)
        print(f"Строка {idx:3d}: {row_text}")

    print("\n" + "=" * 80)
    print("ПОИСК ПАКЕТОВ (те что содержат ключевые слова):")
    print("=" * 80)

    keywords = [
        "niyet", "hikma", "izi", "4u", "premium", "econom",
        "стандарт", "эконом", "comfort",
        "ramadan", "рамадан", "ramazan", "ramad",
        "itikaf", "итикаф", "umrah", "умра"
    ]

    for idx, row in enumerate(data, start=1):
        if not row:
            continue
        row_text = " ".join(row).lower()

        for kw in keywords:
            if kw in row_text:
                print(f"✅ Строка {idx}: {' | '.join(row)} (найдено: '{kw}')")
                break

if __name__ == "__main__":
    inspect_march_sheet()
