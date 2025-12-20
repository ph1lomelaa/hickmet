import asyncio
import os
import sys

sys.path.append(os.getcwd())

from bull_project.bull_bot.config.settings import get_google_client
from bull_project.bull_bot.core.google_sheets.allocator import find_best_slot

# НАСТРОЙКИ
TABLE_ID = "1wyMceL8tASRcI6fXE7zW-Hba-5DTXvQBoVxQlCq-LMk"
SHEET_NAME = "17.12-24.12 Ala-Jed"
PACKAGE_NAME = "17.12-24.12  NIYET акционный /7d"
TARGET_ROOM = "Triple"

def row_col_to_a1(row, col):
    div = col
    string = ""
    while div > 0:
        module = (div - 1) % 26
        string = chr(65 + module) + string
        div = int((div - module) / 26)
    return string + str(row)

async def run_block_test():
    client = get_google_client()
    if not client: return
    ss = client.open_by_key(TABLE_ID)
    ws = ss.worksheet(SHEET_NAME)
    all_values = ws.get_all_values()

    print(f"🔎 Ищу место для {TARGET_ROOM}...")
    row_idx, cols, action = find_best_slot(all_values, PACKAGE_NAME, "M", TARGET_ROOM)

    if not row_idx:
        print("❌ Мест не найдено.")
        return

    print(f"✅ НАЙДЕНО! Строка: {row_idx}. Действие: {action}")

    updates = []
    r_col = cols['room'] # Индекс колонки (0-based)
    col_letter = row_col_to_a1(1, r_col + 1).replace("1", "") # Буква колонки

    # === БЛОЧНАЯ ЗАПИСЬ (Как в новом writer.py) ===
    if action == "trans_2quad_mix":
        print("✨ ПЕРЕСТРАИВАЮ БЛОК 8 СТРОК (2 Quad -> 2 Triple + 1 Double)...")
        # Готовим столбик данных
        values = [
            ['Triple'], [''], [''],   # T
            ['Triple'], [''], [''],   # T
            ['Double'], ['']          # D
        ]
        # Диапазон D40:D47 (например)
        range_str = f"{col_letter}{row_idx}:{col_letter}{row_idx+7}"
        updates.append({'range': range_str, 'values': values})

    # Записываем человека
    l_name_col = cols['last_name'] + 1
    updates.append({'range': row_col_to_a1(row_idx, l_name_col), 'values': [['BLOCK_TEST_USER']]})

    print("🚀 ОТПРАВЛЯЮ БЛОЧНОЕ ОБНОВЛЕНИЕ...")
    ws.batch_update(updates)
    print("✅ ГОТОВО! Теперь структура должна быть идеальной.")

if __name__ == "__main__":
    asyncio.run(run_block_test())