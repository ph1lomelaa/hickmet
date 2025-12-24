from bull_project.bull_bot.core.google_sheets.client import (
    get_google_client,
    get_worksheet_by_title,
)
from bull_project.bull_bot.core.google_sheets.allocator import (
    find_best_slot,
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

        if specific_row:
            pkg_row = find_package_row(all_values, target_pkg)
            if pkg_row is not None:
                for r in range(pkg_row, min(pkg_row + 15, len(all_values))):
                    cols = find_headers_extended(all_values[r])
                    if cols: break
            if not cols: return []

        for i, person_passport in enumerate(group_data):
            gender = person_passport.get('Gender', 'M')

            # --- ПОИСК ---
            if specific_row:
                row_idx = specific_row + i
                action = "manual"
                cols_found = cols
            else:
                row_idx, cols_found, action = find_best_slot(all_values, target_pkg, gender, target_room)
                cols = cols_found

            if row_idx:
                saved_rows.append(row_idx)
                full_data = {**common_data, **person_passport}
                _prepare_updates(updates, row_idx, cols, full_data)

                # Блокируем место в памяти
                if 'last_name' in cols and (row_idx - 1) < len(all_values):
                    all_values[row_idx - 1][cols['last_name']] = "RESERVED"
                    # Сохраняем пол, чтобы следующая итерация видела, кто тут
                    if 'gender' in cols:
                        all_values[row_idx - 1][cols['gender']] = gender

                # --- СТРУКТУРА (ТЕТРИС) ---
                if not is_share and not specific_row:
                    r_col = cols['room']
                    col_letter = row_col_to_a1(1, r_col + 1).replace("1", "")

                    if "trans" in action:
                        print(f"🔧 Тетрис: {action} (стр {row_idx})")

                        if action == "trans_1quad_2dbl":
                            do_transform(ws, updates, merge_tasks, all_values, row_idx, r_col, col_letter, 4, [['Double'], [''], ['Double'], ['']], [(0,1), (2,3)])
                        elif action == "trans_2quad_mix":
                            do_transform(ws, updates, merge_tasks, all_values, row_idx, r_col, col_letter, 8, [['Triple'], [''], [''], ['Triple'], [''], [''], ['Double'], ['']], [(0,2), (3,5), (6,7)])
                        elif action == "trans_2trpl_3dbl":
                            do_transform(ws, updates, merge_tasks, all_values, row_idx, r_col, col_letter, 6, [['Double'], [''], ['Double'], [''], ['Double'], ['']], [(0,1), (2,3), (4,5)])
                        elif action == "trans_3dbl_2trpl":
                            do_transform(ws, updates, merge_tasks, all_values, row_idx, r_col, col_letter, 6, [['Triple'], [''], [''], ['Triple'], [''], ['']], [(0,2), (3,5)])
                        elif action == "trans_2dbl_1quad":
                            do_transform(ws, updates, merge_tasks, all_values, row_idx, r_col, col_letter, 4, [['Quadro'], [''], [''], ['']], [(0,3)])
                        elif action == "trans_1dbl_2sgl":
                            do_transform(ws, updates, merge_tasks, all_values, row_idx, r_col, col_letter, 2, [['Single'], ['Single']], [])
                        elif action == "trans_1trpl_mix":
                            do_transform(ws, updates, merge_tasks, all_values, row_idx, r_col, col_letter, 3, [['Double'], [''], ['Single']], [(0,1)])

                    # Если простое заселение, но название не совпадает (мало ли)
                    elif action == "manual" and not is_share:
                        updates.append({'range': row_col_to_a1(row_idx, r_col + 1), 'values': [[target_room]]})

            else:
                print(f"❌ Место не найдено")

        if updates: ws.batch_update(updates)
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

def _prepare_updates(updates_list, row_idx, cols, data):
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

    for col_key, value in mapping.items():
        if col_key in cols:
            val_str = str(value).strip()
            if not val_str or val_str in ["-", "skip", "None"]: continue
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

        # Находим блок пакета
        header_row, end_row, cols = get_package_block(all_values, package_name)
        if not header_row or not cols:
            print(f"❌ Не найден блок пакета {package_name}")
            return False

        # Отступаем 15 строк от конца блока
        cancelled_row = end_row + 15

        print(f"📝 Записываем отмену в строку {cancelled_row}")

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

        # Находим блок пакета
        header_row, end_row, cols = get_package_block(all_values, package_name)
        if not header_row or not cols:
            print(f"❌ Не найден блок пакета {package_name}")
            return False

        # Отступаем 15 строк от конца блока
        rescheduled_row = end_row + 15

        print(f"📝 Записываем перенос в строку {rescheduled_row}")

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
