#!/usr/bin/env python3
"""Тестируем новую логику поиска пакетов на мартовском листе"""
import sys
sys.path.insert(0, '..')

from bull_project.bull_bot.core.google_sheets.client import get_packages_from_sheet

MARCH_TABLE_ID = "1uQACMT3jkNHOtzWILUa6HFNnP8V_ll96Terxf5XEzMU"
MARCH_SHEET = "07.03-21.03.2026 Ala-Jed"

print("=" * 80)
print("ТЕСТ: Поиск пакетов в мартовском листе")
print("=" * 80)
print(f"\nТаблица: {MARCH_TABLE_ID}")
print(f"Лист: {MARCH_SHEET}")
print("\nВызываю get_packages_from_sheet()...\n")

packages = get_packages_from_sheet(MARCH_TABLE_ID, MARCH_SHEET)

print("=" * 80)
print(f"РЕЗУЛЬТАТ: Найдено {len(packages)} пакетов")
print("=" * 80)

if packages:
    print("\n✅ ПАКЕТЫ НАЙДЕНЫ:\n")
    for row_num, pkg_name in packages.items():
        print(f"  Строка {row_num}: {pkg_name}")
else:
    print("\n❌ ПАКЕТЫ НЕ НАЙДЕНЫ")
    print("\n⚠️ Возможно проблема с логикой поиска")

print("\n" + "=" * 80)
