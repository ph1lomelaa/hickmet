#!/usr/bin/env python3
"""Тестируем что старая логика все еще работает"""
import sys
sys.path.insert(0, '..')

from bull_project.bull_bot.core.google_sheets.client import get_packages_from_sheet

# Используем таблицу из production
JANUARY_TABLE_ID = "15iaUA4J5rgfAz6isS6BA07idUA9dXl-BW15FMw--7Vg"  # JANUARY 2026
JANUARY_SHEET = "07.01-14.01 Ala-Jed/AA/7days "

print("=" * 80)
print("ТЕСТ: Старая логика (январь) - должны найти NIYET, HIKMA и т.д.")
print("=" * 80)
print(f"\nТаблица: {JANUARY_TABLE_ID}")
print(f"Лист: {JANUARY_SHEET}")
print("\nВызываю get_packages_from_sheet()...\n")

packages = get_packages_from_sheet(JANUARY_TABLE_ID, JANUARY_SHEET)

print("=" * 80)
print(f"РЕЗУЛЬТАТ: Найдено {len(packages)} пакетов")
print("=" * 80)

if packages:
    print("\n✅ ПАКЕТЫ НАЙДЕНЫ:\n")
    for row_num, pkg_name in packages.items():
        print(f"  Строка {row_num}: {pkg_name}")
else:
    print("\n❌ ПАКЕТЫ НЕ НАЙДЕНЫ - СТАРАЯ ЛОГИКА СЛОМАЛАСЬ!")

print("\n" + "=" * 80)
