import random
import colorsys
from bull_project.bull_bot.core.google_sheets.client import (
    get_google_client,
    get_worksheet_by_title,
)
from bull_project.bull_bot.core.google_sheets.allocator import (
    check_has_train_column,
    find_package_row,
    find_headers_extended
)

def row_col_to_a1(row, col):
    div = col
    string = ""
    while div > 0:
        module = (div - 1) % 26
        string = chr(65 + module) + string
        div = int((div - module) / 26)
    return string + str(row)

async def save_group_booking(group_data: list, common_data: dict, placement_mode: str, specific_row=None, is_share=False):
    from bull_project.bull_bot.core.google_sheets.allocator import find_best_slot_for_group

    client = get_google_client()
    if not client:
        print("❌ Google client не инициализирован (get_google_client вернул None)")
        return []

    sheet_id = common_data.get('table_id')
    sheet_name = common_data.get('sheet_name')
    target_pkg = common_data['package_name']
    target_room = common_data['room_type']

    try:
        ss = client.open_by_key(sheet_id)
        ws = get_worksheet_by_title(ss, sheet_name)
        all_values = ws.get_all_values()

        saved_rows = []
        updates = []
        cols = None
        merge_tasks = []
        color_tasks = []
        price_tasks = []

        # Пастельный цвет для всей группы (один цвет на всех)
        seed_base = "".join([
            common_data.get("package_name", ""),
            common_data.get("room_type", ""),
            str(len(group_data))
        ])
        rnd = random.Random(seed_base)
        h = rnd.random()
        s = 0.35
        v = 0.95
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        group_color = {"red": r, "green": g, "blue": b}

        # 🔥 ИСПРАВЛЕНИЕ: Используем групповое размещение если паломников больше 1 или режим не specific_row
        if not specific_row and len(group_data) > 0:
            # Используем функцию группового размещения
            saved_rows = find_best_slot_for_group(
                all_values,
                target_pkg,
                group_data,
                target_room,
                placement_mode
            )

            if not saved_rows or len(saved_rows) != len(group_data):
                print(f"❌ Групповое размещение вернуло неполный список строк")
                print(f"   Ожидалось: {len(group_data)}, получено: {len(saved_rows)}")
                return []

            # Получаем колонки для записи данных
            pkg_row = find_package_row(all_values, target_pkg)
            if pkg_row is not None:
                for r in range(pkg_row, min(pkg_row + 15, len(all_values))):
                    cols = find_headers_extended(all_values[r])
                    if cols: break

            if not cols:
                print(f"❌ Не найдены заголовки для пакета {target_pkg}")
                return []

            # Записываем данные для каждого паломника
            for i, (person_passport, row_idx) in enumerate(zip(group_data, saved_rows)):
                full_data = {**common_data, **person_passport}
                _prepare_updates(updates, price_tasks, row_idx, cols, full_data)
                # Планируем окраску имени/фамилии ТОЛЬКО для группы (больше 1 человека)
                if len(group_data) > 1:
                    for key in ("last_name", "first_name"):
                        if key in cols:
                            a1 = row_col_to_a1(row_idx, cols[key] + 1)
                            color_tasks.append(a1)

        elif specific_row:
            # Старая логика для specific_row (ручное размещение)
            pkg_row = find_package_row(all_values, target_pkg)
            if pkg_row is not None:
                for r in range(pkg_row, min(pkg_row + 15, len(all_values))):
                    cols = find_headers_extended(all_values[r])
                    if cols: break
            if not cols: return []

            for i, person_passport in enumerate(group_data):
                row_idx = specific_row + i
                saved_rows.append(row_idx)
                full_data = {**common_data, **person_passport}
                _prepare_updates(updates, price_tasks, row_idx, cols, full_data)
                # Планируем окраску имени/фамилии ТОЛЬКО для группы (больше 1 человека)
                if len(group_data) > 1:
                    for key in ("last_name", "first_name"):
                        if key in cols:
                            a1 = row_col_to_a1(row_idx, cols[key] + 1)
                            color_tasks.append(a1)
        else:
            print(f"❌ Пустой список паломников")
            return []

        if updates: ws.batch_update(updates)
        # Применяем окраску имен/фамилий (один цвет на группу)
        for a1 in color_tasks:
            try:
                ws.format(a1, {"backgroundColor": group_color, "textFormat": {"bold": False}})
            except Exception as e:
                print(f"⚠️ Не удалось окрасить {a1}: {e}")
        # Форматируем цену и оплату
        for row_idx, col_idx in price_tasks:
            a1 = row_col_to_a1(row_idx, col_idx)
            try:
                ws.format(a1, {"numberFormat": {"type": "CURRENCY", "pattern": "[$$]#,##0"}})
            except Exception as e:
                print(f"⚠️ Не удалось применить формат цены для {a1}: {e}")
        if merge_tasks:
            for m_range in merge_tasks:
                try: ws.merge_cells(m_range, merge_type='MERGE_ALL')
                except: pass

        return saved_rows

    except Exception as e:
        print(f"❌ Save error: {e}")
        import traceback
        traceback.print_exc()
        return []

def do_transform(ws, updates, merge_tasks, all_values, start_idx, r_col, col_letter, rows_count, values, merges):
    range_str = f"{col_letter}{start_idx}:{col_letter}{start_idx + rows_count - 1}"
    try: ws.unmerge_cells(range_str)
    except: pass

    updates.append({'range': range_str, 'values': values})

    for m_start, m_end in merges:
        merge_tasks.append(f"{col_letter}{start_idx + m_start}:{col_letter}{start_idx + m_end}")

    # Обновляем память бота (Тип комнаты)
    for k in range(rows_count):
        if start_idx - 1 + k < len(all_values):
            all_values[start_idx - 1 + k][r_col] = values[k][0]

def _prepare_updates(updates_list, price_tasks, row_idx, cols, data):
    # Используем правильные ключи, которые приходят из паспортных данных
    mapping = {
        'last_name': data.get('Last Name', '') or data.get('guest_last_name', ''),
        'first_name': data.get('First Name', '') or data.get('guest_first_name', ''),
        'gender': data.get('Gender', '') or data.get('gender', ''),
        'dob': data.get('Date of Birth', '') or data.get('date_of_birth', ''),
        'doc_num': data.get('Document Number', '') or data.get('passport_num', ''),
        'doc_exp': data.get('Document Expiration', '') or data.get('passport_expiry', ''),
        'iin': data.get('IIN', '') or data.get('guest_iin', ''),
        'visa': data.get('visa_status', ''),
        'avia': data.get('avia', ''),
        'meal': data.get('meal_type', ''),
        'price': data.get('price', ''),
        'amount_paid': data.get('amount_paid', ''),
        'exchange_rate': data.get('exchange_rate', ''),
        'discount': data.get('discount', ''),
        'manager': data.get('manager_name_text', ''),
        'comment': data.get('comment', ''),
        'client_phone': data.get('client_phone', ''),
        'train': data.get('train', ''),
        'region': data.get('region', ''),
        'source': data.get('source', '')
    }

    # Отладка для train - проверяем есть ли колонка в таблице
    if "train" in mapping and "train" not in cols:
        print(f"⚠️ TRAIN: Колонка 'train' НЕ найдена в таблице! Доступные колонки: {list(cols.keys())}")
    elif "train" in mapping and "train" in cols:
        print(f"✅ TRAIN: Колонка 'train' найдена в таблице (индекс {cols['train']}), значение = '{mapping.get('train')}'")

    for col_key, value in mapping.items():
        if col_key in cols:
            val_str = str(value).strip()
            if not val_str or val_str in ["-", "skip", "None"]:
                # Отладка для train
                if col_key == "train":
                    print(f"⚠️ TRAIN пропущен: значение = '{val_str}'")
                continue
            # Отладка для train
            if col_key == "train":
                print(f"✅ TRAIN будет записан: значение = '{val_str}'")
            # Цена и оплата — записываем как число и отмечаем для форматирования
            if col_key in ("price", "amount_paid"):
                clean = val_str.replace("$", "").replace(" ", "").replace(",", "")
                try:
                    num_val = float(clean)
                    price_tasks.append((row_idx, cols[col_key] + 1))
                    updates_list.append({'range': f"{row_col_to_a1(row_idx, cols[col_key] + 1)}", 'values': [[num_val]]})
                except:
                    updates_list.append({'range': f"{row_col_to_a1(row_idx, cols[col_key] + 1)}", 'values': [[val_str]]})
            else:
                updates_list.append({'range': f"{row_col_to_a1(row_idx, cols[col_key] + 1)}", 'values': [[val_str]]})

async def save_booking_smart(booking_data):
    passport_data = {
        'Last Name': booking_data.get('last_name'), 'First Name': booking_data.get('first_name'),
        'Gender': booking_data.get('gender'), 'Date of Birth': booking_data.get('dob'),
        'Document Number': booking_data.get('passport_num'), 'Document Expiration': booking_data.get('passport_exp')
    }
    rows = await save_group_booking([passport_data], booking_data, 'separate')
    return rows[0] if rows else False

async def check_train_exists(sheet_id, sheet_name, package_name):
    client = get_google_client()
    if not client: return False
    try:
        ss = client.open_by_key(sheet_id); ws = get_worksheet_by_title(ss, sheet_name); all_values = ws.get_all_values()
        return check_has_train_column(all_values, package_name)
    except: return False

async def clear_booking_in_sheets(sheet_id, sheet_name, row_number, package_name):
    client = get_google_client()
    if not client or not row_number: return False
    try:
        ss = client.open_by_key(sheet_id); ws = get_worksheet_by_title(ss, sheet_name); all_values = ws.get_all_values()
        pkg_row = find_package_row(all_values, package_name); cols = None
        if pkg_row is not None:
            for r in range(pkg_row, min(pkg_row + 30, len(all_values))):
                cols = find_headers_extended(all_values[r])
                if cols: break
        if not cols: return False
        fields_to_clear = ['last_name', 'first_name', 'gender', 'dob', 'doc_num', 'doc_exp', 'price', 'comment', 'manager', 'train', 'client_phone']
        updates = []
        for key in fields_to_clear:
            if key in cols: updates.append({'range': f"{row_col_to_a1(row_number, cols[key] + 1)}", 'values': [['']]})
        if updates: ws.batch_update(updates); return True
        return False
    except: return False

def find_last_content_row(all_values):
    """Находит последнюю строку с содержимым на листе"""
    for r in range(len(all_values) - 1, -1, -1):
        row_text = "".join([str(c).strip() for c in all_values[r]])
        if len(row_text) > 2:  # Есть какой-то контент
            return r + 1  # +1 потому что индексы с 0
    return len(all_values)

async def write_cancelled_booking_red(sheet_id, sheet_name, package_name, guest_name):
    from bull_project.bull_bot.core.google_sheets.allocator import get_package_block
    client = get_google_client()
    if not client:
        print("❌ Google client не инициализирован")
        return False

    try:
        ss = client.open_by_key(sheet_id)
        ws = get_worksheet_by_title(ss, sheet_name)
        all_values = ws.get_all_values()

        # Находим блок пакета (нужно для получения колонки)
        _, _, cols = get_package_block(all_values, package_name)
        if not cols:
            print(f"❌ Не найден блок пакета {package_name}")
            return False

        # 🔥 НАХОДИМ ПОСЛЕДНЮЮ СТРОКУ НА ВСЕМ ЛИСТЕ
        last_row = find_last_content_row(all_values)
        # Отступаем 15 строк от конца ВСЕГО листа
        cancelled_row = last_row + 15

        print(f"📝 Записываем отмену в строку {cancelled_row} (последняя строка листа: {last_row})")

        # Находим колонку для записи имени
        name_col = cols.get('last_name')
        if not name_col:
            print("❌ Не найдена колонка для имени")
            return False

        # Записываем имя
        cell_range = row_col_to_a1(cancelled_row, name_col + 1)
        ws.update(cell_range, [[f"❌ ОТМЕНЕНО: {guest_name}"]])

        # Форматируем красным цветом
        ws.format(cell_range, {
            "backgroundColor": {
                "red": 1.0,
                "green": 0.8,
                "blue": 0.8
            },
            "textFormat": {
                "foregroundColor": {
                    "red": 0.8,
                    "green": 0.0,
                    "blue": 0.0
                },
                "fontSize": 11,
                "bold": True
            }
        })

        print(f"✅ Отмена записана красным в строку {cancelled_row}")
        return True

    except Exception as e:
        print(f"❌ Ошибка записи отмены: {e}")
        import traceback
        traceback.print_exc()
        return False

async def write_rescheduled_booking_red(sheet_id, sheet_name, package_name, guest_name):
    """Записывает перенос красным цветом внизу блока пакета"""
    from bull_project.bull_bot.core.google_sheets.allocator import get_package_block
    client = get_google_client()
    if not client:
        print("❌ Google client не инициализирован")
        return False

    try:
        ss = client.open_by_key(sheet_id)
        ws = get_worksheet_by_title(ss, sheet_name)
        all_values = ws.get_all_values()

        # Находим блок пакета (нужно для получения колонки)
        _, _, cols = get_package_block(all_values, package_name)
        if not cols:
            print(f"❌ Не найден блок пакета {package_name}")
            return False

        # 🔥 НАХОДИМ ПОСЛЕДНЮЮ СТРОКУ НА ВСЕМ ЛИСТЕ
        last_row = find_last_content_row(all_values)
        # Отступаем 15 строк от конца ВСЕГО листа
        rescheduled_row = last_row + 15

        print(f"📝 Записываем перенос в строку {rescheduled_row} (последняя строка листа: {last_row})")

        # Находим колонку для записи имени
        name_col = cols.get('last_name')
        if not name_col:
            print("❌ Не найдена колонка для имени")
            return False

        # Записываем имя
        cell_range = row_col_to_a1(rescheduled_row, name_col + 1)
        ws.update(cell_range, [[f"♻️ ПЕРЕНОС: {guest_name}"]])

        # Форматируем красным цветом (как отмена)
        ws.format(cell_range, {
            "backgroundColor": {
                "red": 1.0,
                "green": 0.8,
                "blue": 0.8
            },
            "textFormat": {
                "foregroundColor": {
                    "red": 0.8,
                    "green": 0.0,
                    "blue": 0.0
                },
                "fontSize": 11,
                "bold": True
            }
        })

        print(f"✅ Перенос записан красным в строку {rescheduled_row}")
        return True

    except Exception as e:
        print(f"❌ Ошибка записи переноса: {e}")
        import traceback
        traceback.print_exc()
        return False
