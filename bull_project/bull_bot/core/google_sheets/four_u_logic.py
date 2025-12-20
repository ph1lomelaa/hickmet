import re
from bull_project.bull_bot.config.settings import get_google_client

# Заголовки для нового листа (16 колонок)
HEADERS_4U = [
    '№', 'Avia', 'Visa', 'Type of room', 'Meal a day', 'Last Name', 'First Name',
    'Gender', 'Date of Birth', 'Document Number', 'Document Issue date',
    'Document Expiration', 'Price', 'Comment', 'Manager', 'Train'
]

# === 1. ПОИСК СВОБОДНЫХ МЕСТ (СКАНЕР) ===

async def find_availability_for_4u(table_id, target_date, needed_count, needed_room):
    """
    Ищет, в каких пакетах на листах с похожей датой есть свободные места.
    """
    client = get_google_client()
    ss = client.open_by_key(table_id)

    results = []

    # Берем "13.12" из "13.12-20.12" для поиска листа
    search_date = target_date.split("-")[0].strip()

    print(f"🔎 Ищу листы с датой: {search_date}")

    for ws in ss.worksheets():
        # Фильтр: ищем листы, где в названии есть "13.12"
        if search_date not in ws.title:
            continue

        all_values = ws.get_all_values()

        current_pkg = "Неизвестный пакет"
        free_counter = 0
        start_free_row = None

        # Индекс колонки с фамилией (обычно F = 5)
        L_NAME_COL = 5

        for i, row in enumerate(all_values):
            row_num = i + 1
            row_text = " ".join(row).lower()

            # 1. Пытаемся поймать название пакета (по ключевым словам)
            # Обычно это объединенная ячейка в начале, где есть слово "hotel" или "days"
            if "hotel" in row_text or "days" in row_text or "умра" in row_text:
                # Если у нас накопились свободные места в ПРЕДЫДУЩЕМ пакете - сохраняем
                if free_counter >= needed_count and start_free_row:
                    results.append({
                        'sheet': ws.title,
                        'package': current_pkg,
                        'free': free_counter,
                        'rows_to_clear': f"{start_free_row}-{start_free_row + free_counter - 1}"
                    })

                # Обновляем имя текущего пакета
                # Обычно имя в первой непустой ячейке
                pkg_candidate = row[0] if row[0] else (row[1] if len(row)>1 else "")
                if len(pkg_candidate) > 5:
                    current_pkg = pkg_candidate

                # Сбрасываем счетчики
                free_counter = 0
                start_free_row = None
                continue

            # 2. Проверяем, это строка с данными или заголовок?
            # Если это заголовок (есть "Last Name"), пропускаем
            if "last name" in row_text or "фамилия" in row_text:
                continue

            # 3. Проверка на пустоту
            # Берем значение фамилии. Если меньше 2 символов - считаем пустым.
            l_name = row[L_NAME_COL] if len(row) > L_NAME_COL else ""
            is_empty = len(l_name.strip()) < 2

            if is_empty:
                # Это пустая строка
                if start_free_row is None:
                    start_free_row = row_num
                free_counter += 1
            else:
                # Цепочка прервалась (встретили занятую строку)
                if free_counter >= needed_count:
                    results.append({
                        'sheet': ws.title,
                        'package': current_pkg,
                        'free': free_counter,
                        'rows_to_clear': f"{start_free_row}-{start_free_row + free_counter - 1}"
                    })
                free_counter = 0
                start_free_row = None

        # Проверяем в самом конце листа (если таблица закончилась пустыми строками)
        if free_counter >= needed_count and start_free_row:
            results.append({
                'sheet': ws.title,
                'package': current_pkg,
                'free': free_counter,
                'rows_to_clear': f"{start_free_row}-{start_free_row + free_counter - 1}"
            })

    return results

# === 2. СОЗДАНИЕ ЛИСТА 4U (ВАШ КОД + ОФОРМЛЕНИЕ) ===

async def create_4u_sheet(table_id, date_str, pilgrim_count, room_type, manager_name):
    client = get_google_client()
    ss = client.open_by_key(table_id)

    # 1. Позиция листа (после похожего)
    target_start_date = date_str.split("-")[0].strip()
    insert_index = 0
    worksheets = ss.worksheets()
    for ws in worksheets:
        if ws.title.strip().startswith(target_start_date):
            insert_index = ws.index + 1

    if insert_index == 0 and len(worksheets) > 0:
        insert_index = len(worksheets)

    new_title = f"{date_str} / 4U {manager_name}"

    try:
        ws = ss.add_worksheet(title=new_title, rows=pilgrim_count + 20, cols=20, index=insert_index)
    except:
        try:
            new_title += " (2)"
            ws = ss.add_worksheet(title=new_title, rows=pilgrim_count + 20, cols=20, index=insert_index)
        except:
            return False, "Ошибка: Лист существует!"

    # 2. Данные
    data = []
    # A1: Заголовок
    data.append([f"{date_str} / 4U"])
    # A2: Шапка
    data.append(HEADERS_4U)

    # Данные
    for i in range(pilgrim_count):
        row = [''] * len(HEADERS_4U)
        row[0] = str(i + 1)      # №
        row[3] = room_type       # Type of room
        row[14] = manager_name   # Manager
        row[15] = "YES"          # Train
        data.append(row)

    ws.update('A1', data)

    # 3. Дизайн (Batch Update)
    sheet_id = ws.id
    requests = []

    # Merge A1:G1 + Стиль заголовка
    requests.append({
        "mergeCells": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 7},
            "mergeType": "MERGE_ALL"
        }
    })
    requests.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 7},
            "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER", "textFormat": {"fontSize": 17, "bold": True}}},
            "fields": "userEnteredFormat(horizontalAlignment,textFormat)"
        }
    })

    # Рамки для шапки (A2:P2)
    requests.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": len(HEADERS_4U)},
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {"bold": True},
                    "borders": {
                        "top": {"style": "SOLID"}, "bottom": {"style": "SOLID"}, "left": {"style": "SOLID"}, "right": {"style": "SOLID"}
                    }
                }
            },
            "fields": "userEnteredFormat(textFormat,borders)"
        }
    })

    # Merge комнат (Только Type of room)
    rt = room_type.lower()
    room_size = 4 if 'quad' in rt else (3 if 'trip' in rt else (2 if 'doub' in rt else 1))

    start_row = 2
    for i in range(0, pilgrim_count, room_size):
        limit = min(i + room_size, pilgrim_count)
        if limit - i > 1:
            requests.append({
                "mergeCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": start_row + i, "endRowIndex": start_row + limit,
                        "startColumnIndex": 3, "endColumnIndex": 4
                    },
                    "mergeType": "MERGE_ALL"
                }
            })

    if requests:
        ss.batch_update({"requests": requests})

    return True, new_title