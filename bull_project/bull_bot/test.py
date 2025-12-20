import sys
import os
import asyncio
from datetime import datetime

# === 1. НАСТРОЙКА ПУТЕЙ ===
# Добавляем текущую папку, чтобы Python увидел ваш проект
sys.path.append(os.getcwd())

try:
    # Импортируем функции из вашего client.py
    from bull_project.bull_bot.core.google_sheets.client import (
        get_accessible_tables,
        get_sheet_names,
        get_packages_from_sheet
    )
except ImportError as e:
    print("❌ ОШИБКА ИМПОРТА:")
    print(e)
    print("\n💡 СОВЕТ: Запускайте файл из корневой папки проекта командой:")
    print("python test_search.py")
    sys.exit(1)

# === 2. СЛОВАРЬ МЕСЯЦЕВ (Для поиска таблицы) ===
MONTHS_RU = {
    1: ['янв', 'jan', '01'], 2: ['фев', 'feb', '02'],
    3: ['мар', 'mar', '03'], 4: ['апр', 'apr', '04'],
    5: ['май', 'may', '05'], 6: ['июн', 'jun', '06'],
    7: ['июл', 'jul', '07'], 8: ['авг', 'aug', '08'],
    9: ['сен', 'sep', '09'], 10: ['окт', 'oct', '10'],
    11: ['ноя', 'nov', '11'], 12: ['дек', 'dec', '12']
}

async def run_test_logic(date_input: str):
    print(f"\n🔎 --- АНАЛИЗ ДАТЫ: {date_input} ---")

    current_year = datetime.now().year

    # --- ШАГ 1: ПАРСИНГ ДАТЫ ---
    try:
        txt = date_input.strip().replace("/", ".")
        if "." not in txt:
            # Если ввели только число "20"
            today = datetime.now()
            search_dt = datetime(current_year, today.month, int(txt))
        else:
            # Если ввели "20.12"
            search_dt = datetime.strptime(f"{txt}.{current_year}", "%d.%m.%Y")

        day_str = search_dt.strftime("%d.%m") # "20.12"
        month_num = search_dt.month
        month_keys = MONTHS_RU.get(month_num, [])

        print(f"✅ Дата понятна: {day_str} (Месяц #{month_num}, ключи: {month_keys})")

    except ValueError:
        print("❌ Ошибка: Неверный формат даты. Попробуйте '15.12'")
        return

    # --- ШАГ 2: ПОИСК ТАБЛИЦЫ ---
    print("\n📂 [Шаг 1] Сканирую таблицы...")
    tables = get_accessible_tables() # Получаем словарь {Название: ID}

    if not tables:
        print("❌ Ошибка: Не удалось получить список таблиц (проверьте ключи/интернет).")
        return

    target_table_id = None
    target_table_name = ""

    for title, t_id in tables.items():
        title_lower = title.lower()
        # Ищем совпадение месяца (например "дек" в "Декабрь 2024")
        if any(key in title_lower for key in month_keys):
            target_table_id = t_id
            target_table_name = title
            print(f"   🟢 Нашел таблицу: '{title}'")
            break

    if not target_table_id:
        print(f"❌ Не нашел таблицу для месяца {month_num}.")
        return

    # --- ШАГ 3: ПОИСК ВСЕХ ЛИСТОВ ---
    print(f"\n📄 [Шаг 2] Ищу ВСЕ листы на дату '{day_str}' внутри '{target_table_name}'...")
    sheets = get_sheet_names(target_table_id)

    if not sheets:
        print("❌ В таблице нет листов.")
        return

    found_sheets = []
    for s in sheets:
        if s.strip().startswith(day_str):
            found_sheets.append(s)
            print(f"   🟢 Нашел лист: '{s}'")

    if not found_sheets:
        print(f"❌ Листов, начинающихся на '{day_str}', не найдено.")
        return

    # --- ШАГ 4: СБОР ПАКЕТОВ СО ВСЕХ ЛИСТОВ ---
    print(f"\n📦 [Шаг 3] Собираю пакеты со всех найденных листов...")

    total_packages = []

    for sheet_name in found_sheets:
        print(f"   scanning -> {sheet_name}...")
        packages_map = get_packages_from_sheet(target_table_id, sheet_name)

        if packages_map:
            for pkg_name in packages_map.values():
                # Добавляем "хвост" с названием листа, если он отличается от даты
                # Например: из "15.12 Алматы" делаем "Swiss [Алматы]"
                suffix = sheet_name.replace(day_str, "").strip(" -/|")

                if suffix:
                    display_name = f"{pkg_name} [{suffix}]"
                else:
                    display_name = pkg_name

                # Формат для Web App: "ИмяПакета::ИмяЛиста"
                full_value = f"{display_name}::{sheet_name}"
                total_packages.append(full_value)
                print(f"      🔹 Нашел: {display_name}")
        else:
            print("      ⚠️ Пусто")

    # --- ИТОГ ---
    print("\n🏁 --- РЕЗУЛЬТАТ ДЛЯ WEB APP ---")
    if not total_packages:
        print("❌ Пакеты не найдены ни на одном листе.")
    else:
        print(f"✅ Всего пакетов: {len(total_packages)}")
        print("Список для выпадающего меню:")
        for p in total_packages:
            print(f" - {p}")

# === ЗАПУСК ===
if __name__ == "__main__":
    print("🤖 ТЕСТ ПОИСКА (MULTI-SHEET)")
    print("Напишите дату, чтобы проверить поиск по всем листам.")

    while True:
        user_in = input("\n✍️ Введите дату (например 15.12) или 'q': ")
        if user_in.lower() in ['q', 'exit']:
            break

        asyncio.run(run_test_logic(user_in))