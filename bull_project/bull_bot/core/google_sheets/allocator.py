import re
from bull_project.bull_bot.core.parsers.people_parser import _norm_room_kind

def normalize(text):
    return str(text).replace("\n", " ").replace("\r", " ").strip().lower()

# === КАРТА ЗАГОЛОВКОВ ===
HEADER_MAP = {
    "last_name": ["last name", "lastname", "фамилия", "names"],
    "first_name": ["first name", "firstname", "имя"],
    "gender": ["gender", "sex", "пол"],
    "room": ["type of room", "room", "тип номера", "комната"],
    "meal": ["meal", "meal a day", "питание"],
    "dob": ["date of birth", "dob", "дата рождения", "д.р."],
    "doc_num": ["document number", "passport", "номер паспорта", "passport number", "doc num"],
    "doc_exp": ["document expiration", "expiration", "expiry", "срок действия", "годен до", "valid until"],
    "iin": ["iin", "ИИН", "иин"],
    "visa": ["visa", "виза"],
    "avia": ["avia", "авиа", "рейс", "flight"],
    "price": ["price", "цена", "стоимость"],
    "comment": ["comment", "комментарий", "примечание", "сomment"],
    "manager": ["manager", "менеджер"],
    "train": ["train", "поезд", "жд"],
    "client_phone": ["contact", "phone", "телефон", "номер", "контакты"],
    "source": ["source", "источник"],
    "amount_paid": ["paid", "оплачено", "внесено"],
    "region": ["region", "регион"],
}

ROOM_FALLBACKS = {
    "quad": ["quad", "dbl"],
    "trpl": ["trpl", "quad", "dbl"],
    "dbl": ["dbl", "quad", "trpl"],
    "sgl": ["sgl", "dbl", "trpl"],
    "quin": ["quin", "quad", "dbl"],
}

def normalize_room_value(value):
    """Нормализует тип комнаты, приходящий от пользователя."""
    print(f"\n🔧 normalize_room_value вызвана с: '{value}'")
    if not value:
        print(f"   ❌ Значение пустое, возвращаем ''")
        return ""
    normalized = _norm_room_kind(str(value), None)
    print(f"   📊 _norm_room_kind вернула: '{normalized}'")
    if normalized:
        print(f"   ✅ Возвращаем normalized: '{normalized}'")
        return normalized
    fallback = normalize(value)
    print(f"   ⚠️ normalized пустой, возвращаем fallback: '{fallback}'")
    return fallback

def find_package_row(all_rows, target_pkg_name):
    """Поиск строки с названием пакета"""
    target = normalize(target_pkg_name)
    print(f"🔍 Ищем пакет: '{target}'")

    for i, row in enumerate(all_rows):
        row_text = normalize(" ".join(row[:5]))
        if target in row_text:
            print(f"✅ Найден пакет в строке {i+1}: {row_text[:100]}")
            return i

    # Попытка найти по ключевому слову
    parts = target.split()
    if len(parts) > 1:
        keyword = parts[-1]
        for i, row in enumerate(all_rows):
            row_text = normalize(" ".join(row[:5]))
            if keyword in row_text and any(c.isdigit() for c in row_text):
                print(f"✅ Найден пакет (по ключевому слову) в строке {i+1}")
                return i

    print(f"❌ Пакет '{target}' не найден!")
    return None

def find_headers_extended(row):
    """Поиск заголовков таблицы"""
    cols = {}
    row_clean = [normalize(c) for c in row]

    # Проверяем наличие хотя бы одного из ключевых заголовков
    has_name_col = any(kw in " ".join(row_clean) for kw in ["last name", "фамилия", "names", "name"])

    if not has_name_col:
        return None

    for col_idx, val in enumerate(row_clean):
        if not val:
            continue
        for key, keywords in HEADER_MAP.items():
            if key not in cols and any(k == val or k in val for k in keywords):
                cols[key] = col_idx

    # Должна быть колонка "room" и хотя бы одна из: last_name/first_name/gender
    if "room" in cols and (cols.get("last_name") or cols.get("first_name") or cols.get("gender")):
        print(f"✅ Заголовки найдены: {list(cols.keys())}")
        return cols

    return None

def get_package_block(all_rows, pkg_name):
    """Получение границ блока пакета"""
    start_row = find_package_row(all_rows, pkg_name)
    if start_row is None:
        print(f"❌ Пакет '{pkg_name}' не найден в таблице")
        return None, None, None

    header_row = None
    cols = None

    # Ищем заголовки в пределах 15 строк после названия пакета
    for r in range(start_row, min(start_row + 15, len(all_rows))):
        cols = find_headers_extended(all_rows[r])
        if cols:
            header_row = r
            print(f"✅ Заголовки найдены в строке {r+1}")
            break

    if not header_row:
        print(f"❌ Заголовки не найдены для пакета '{pkg_name}'")
        return None, None, None

    # Определяем конец блока
    end_row = len(all_rows)
    empty_streak = 0

    for r in range(header_row + 1, len(all_rows)):
        row_text = "".join([str(c).strip() for c in all_rows[r]])
        if len(row_text) < 2:
            empty_streak += 1
            if empty_streak >= 3:
                end_row = r - empty_streak + 1
                break
        else:
            empty_streak = 0
            norm_text = normalize(row_text)
            # Проверка на начало нового пакета
            if "days" in norm_text or ("-" in norm_text and "202" in norm_text and len(norm_text) < 50):
                end_row = r
                break

    print(f"📦 Блок пакета: строки {header_row+1} - {end_row}")
    return header_row, end_row, cols

def check_has_train_column(all_rows, pkg_name):
    _, _, cols = get_package_block(all_rows, pkg_name)
    return cols and 'train' in cols

def get_room_size(room_text):
    """Определение размера комнаты"""
    t = normalize(room_text)
    if 'quad' in t or '4' in t: return 4
    if 'trip' in t or 'trpl' in t or '3' in t: return 3
    if 'doub' in t or 'dbl' in t or '2' in t: return 2
    if 'sing' in t or 'sgl' in t or '1' in t: return 1
    return 1

def is_row_occupied(row, col_last, col_first=None):
    """Проверка занятости строки"""
    l_name = row[col_last] if col_last < len(row) else ""
    f_name = row[col_first] if col_first and col_first < len(row) else ""
    return len(normalize(l_name)) > 0 or len(normalize(f_name)) > 0

def check_rows_are_empty(all_rows, start_idx, count, col_last):
    """Проверка, что N строк подряд пустые"""
    for i in range(count):
        r_idx = start_idx + i
        if r_idx >= len(all_rows):
            return False
        if is_row_occupied(all_rows[r_idx], col_last):
            return False
    return True

def find_share_slot_for_type(all_rows, header_row, end_row, cols, room_type, target_gender, require_existing=False):
    """Поиск свободного места в комнатах указанного типа"""
    col_room = cols.get("room")
    col_last = cols.get("last_name")
    col_first = cols.get("first_name")
    col_gender = cols.get("gender")

    if col_room is None or col_last is None:
        return None

    target_gen = normalize(target_gender).upper()

    for i in range(header_row + 1, end_row):
        row = all_rows[i]
        raw_room = normalize(row[col_room]) if col_room < len(row) else ""
        if not raw_room:
            continue

        current_room = _norm_room_kind(raw_room, None)
        if current_room != room_type:
            continue

        room_size = get_room_size(raw_room)
        first_free_idx = None
        room_gender = None
        has_guests = False
        compatible = True

        for k in range(room_size):
            curr_idx = i + k
            if curr_idx >= len(all_rows):
                break

            c_row = all_rows[curr_idx]
            occupied = is_row_occupied(c_row, col_last, col_first)
            gen = c_row[col_gender] if col_gender and col_gender < len(c_row) else ""
            norm_gen = normalize(gen).upper() if gen else ""

            if occupied:
                has_guests = True
                if norm_gen and room_gender and room_gender != norm_gen:
                    compatible = False
                    break
                if norm_gen:
                    room_gender = norm_gen
                if norm_gen and norm_gen not in ['M', 'F']:
                    room_gender = norm_gen
                if norm_gen and target_gen in ['M', 'F'] and norm_gen != target_gen:
                    compatible = False
                    break
            else:
                if first_free_idx is None:
                    first_free_idx = curr_idx

        if not compatible or first_free_idx is None:
            continue
        if require_existing and not has_guests:
            continue

        return first_free_idx + 1

    return None

# ==================== 🔥 ГЛАВНЫЙ ПОИСК С ПОДДЕРЖКОЙ ГРУППОВОГО РАЗМЕЩЕНИЯ ====================

def find_best_slot_for_group(all_rows, target_pkg_name, group_data, target_room_type, placement_type="separate"):
    """
    Поиск места для группы паломников
    
    Args:
        all_rows: Все строки таблицы
        target_pkg_name: Название пакета
        group_data: Список словарей с данными паломников (должны содержать 'Gender')
        target_room_type: Тип комнаты
        placement_type: "family" (вместе) или "separate" (по полу)
    
    Returns:
        list: Список строк для размещения каждого паломника
    """
    print(f"\n{'='*60}")
    print(f"🔍 ГРУППОВОЕ РАЗМЕЩЕНИЕ")
    print(f"   Пакет: {target_pkg_name}")
    print(f"   Количество: {len(group_data)}")
    print(f"   Тип комнаты: {target_room_type}")
    print(f"   Режим: {placement_type}")
    print(f"{'='*60}\n")

    header_row, end_row, cols = get_package_block(all_rows, target_pkg_name)
    if not header_row:
        print("❌ Не удалось найти блок пакета")
        return []

    col_room = cols.get("room")
    col_last = cols.get("last_name")
    col_first = cols.get("first_name")
    col_gender = cols.get("gender")

    if col_room is None or col_last is None:
        print(f"❌ Отсутствуют необходимые колонки")
        return []

    target_room = normalize_room_value(target_room_type)
    group_size = len(group_data)
    fallback_types = ROOM_FALLBACKS.get(target_room, [target_room])
    
    # Разделяем группу по полу
    males = [p for p in group_data if normalize(p.get('Gender', 'M')).upper() == 'M']
    females = [p for p in group_data if normalize(p.get('Gender', 'M')).upper() == 'F']
    
    print(f"👥 Состав группы: {len(males)} мужчин, {len(females)} женщин")

    result_rows = []

    if placement_type == "family":
        # РЕЖИМ "СЕМЬЯ" - размещаем всех вместе, не смотря на пол
        print("\n👪 Режим 'СЕМЬЯ' - ищем место для всей группы вместе")

        # Ищем свободную комнату нужного размера
        room_capacity = get_room_size(target_room)

        # СПЕЦИАЛЬНЫЙ СЛУЧАЙ: если 1 человек, пытаемся сначала подселить ТОЛЬКО в точный тип
        if group_size == 1:
            print("\n🔍 Один человек - пытаемся найти свободное место")
            person_gender = group_data[0].get('Gender', 'M') if group_data else 'M'
            gender_norm = normalize(person_gender).upper()

            # ШАГ 1: Ищем свободное место ТОЛЬКО в точном типе комнаты (quad)
            print(f"   Шаг 1: Поиск свободного места в комнатах типа {target_room}")
            share_slot = find_share_slot_for_type(
                all_rows, header_row, end_row, cols, target_room, gender_norm, require_existing=False
            )
            if share_slot:
                print(f"   ✅ Найдено место в комнате {target_room} в строке {share_slot}")
                result_rows.append(share_slot)
                idx = share_slot - 1
                if idx < len(all_rows):
                    all_rows[idx][col_last] = "RESERVED"
                    if col_gender:
                        all_rows[idx][col_gender] = gender_norm
                print(f"\n✅ Группа размещена! Строки: {result_rows}")
                return result_rows

            # ШАГ 2: Ищем пустую комнату точного типа
            print(f"   Шаг 2: Поиск пустой комнаты типа {target_room}")
            empty_slot = find_empty_room_slot(all_rows, header_row, end_row, cols, target_room)
            if empty_slot:
                print(f"   ✅ Найдена пустая комната {target_room} в строке {empty_slot}")
                result_rows.append(empty_slot)
                idx = empty_slot - 1
                if idx < len(all_rows):
                    all_rows[idx][col_last] = "RESERVED"
                    if col_gender:
                        all_rows[idx][col_gender] = gender_norm
                print(f"\n✅ Группа размещена! Строки: {result_rows}")
                return result_rows

            # ШАГ 3: НЕТ СВОБОДНЫХ QUAD - пробуем трансформацию или fallback
            print(f"   ❌ Нет свободных мест в комнатах типа {target_room}")
            print(f"   Шаг 3: Пробуем трансформацию или fallback типы")
            fallback_slot, _, mode = find_best_slot(all_rows, target_pkg_name, gender_norm, target_room_type)
            if fallback_slot:
                result_rows.append(fallback_slot)
                idx = fallback_slot - 1
                if idx < len(all_rows):
                    all_rows[idx][col_last] = "RESERVED"
                    if col_gender:
                        all_rows[idx][col_gender] = gender_norm
                print(f"   ✅ Найден слот через {mode}: строка {fallback_slot}")
                print(f"\n✅ Группа размещена! Строки: {result_rows}")
                return result_rows

            print("   ❌ Не удалось найти место даже через трансформацию")
            return []

        if group_size > room_capacity:
            print(f"⚠️ Группа ({group_size}) больше вместимости комнаты ({room_capacity})")
            # Нужно несколько комнат
            needed_rooms = (group_size + room_capacity - 1) // room_capacity
            print(f"   Требуется комнат: {needed_rooms}")
            
            placed_count = 0
            for _ in range(needed_rooms):
                # Ищем пустую комнату
                slot = find_empty_room_slot(all_rows, header_row, end_row, cols, target_room)
                if slot:
                    # Размещаем людей в эту комнату
                    people_in_this_room = min(room_capacity, group_size - placed_count)
                    for j in range(people_in_this_room):
                        result_rows.append(slot + j)
                    placed_count += people_in_this_room
                    
                    # Блокируем место в памяти
                    for j in range(people_in_this_room):
                        if (slot + j - 1) < len(all_rows):
                            all_rows[slot + j - 1][col_last] = "RESERVED"
                else:
                    print(f"❌ Не удалось найти свободную комнату")
                    return []
        else:
            # Группа помещается в одну комнату
            slot = find_empty_room_slot(all_rows, header_row, end_row, cols, target_room)
            if slot:
                for j in range(group_size):
                    result_rows.append(slot + j)
                    # Блокируем место
                    if (slot + j - 1) < len(all_rows):
                        all_rows[slot + j - 1][col_last] = "RESERVED"
            else:
                print(f"❌ Не удалось найти свободную комнату")
                return []

    else:
        # РЕЖИМ "РАЗДЕЛЬНО" - размещаем по полу
        print("\n🚻 Режим 'РАЗДЕЛЬНО' - размещаем мужчин и женщин отдельно")

        # 🔥 ИСПРАВЛЕНИЕ: Сохраняем индексы каждого человека в исходном списке
        male_indices = []
        female_indices = []

        for idx, person in enumerate(group_data):
            gender = normalize(person.get('Gender', 'M')).upper()
            if gender == 'M':
                male_indices.append(idx)
            else:
                female_indices.append(idx)

        # Размещаем мужчин
        male_rows = []
        if males:
            print(f"\n👨 Размещаем {len(males)} мужчин:")
            male_rows = place_gender_group(all_rows, header_row, end_row, cols, males, 'M', target_room)
            if not male_rows or len(male_rows) != len(males):
                print(f"❌ Не удалось разместить всех мужчин")
                return []

        # Размещаем женщин
        female_rows = []
        if females:
            print(f"\n👩 Размещаем {len(females)} женщин:")
            female_rows = place_gender_group(all_rows, header_row, end_row, cols, females, 'F', target_room)
            if not female_rows or len(female_rows) != len(females):
                print(f"❌ Не удалось разместить всех женщин")
                return []

        # 🔥 ИСПРАВЛЕНИЕ: Восстанавливаем правильный порядок строк
        # Создаем список нужного размера
        result_rows = [None] * len(group_data)

        # Размещаем мужчин на их исходные позиции
        for i, original_idx in enumerate(male_indices):
            result_rows[original_idx] = male_rows[i]

        # Размещаем женщин на их исходные позиции
        for i, original_idx in enumerate(female_indices):
            result_rows[original_idx] = female_rows[i]

        print(f"\n✅ Порядок восстановлен:")
        for idx, (person, row) in enumerate(zip(group_data, result_rows)):
            gender = person.get('Gender', 'M')
            print(f"   {idx+1}. Пол {gender} → строка {row}")

    print(f"\n✅ Группа размещена! Строки: {result_rows}")
    return result_rows


def place_gender_group(all_rows, header_row, end_row, cols, people, gender, target_room):
    """Размещение группы одного пола"""
    col_room = cols.get("room")
    col_last = cols.get("last_name")
    col_first = cols.get("first_name")
    col_gender = cols.get("gender")
    
    result_rows = []
    people_placed = 0
    group_size = len(people)
    
    print(f"   Ищем места для {group_size} человек пола {gender}")
    
    # Сначала пытаемся подселить в существующие комнаты
    for i in range(header_row + 1, end_row):
        if people_placed >= group_size:
            break
            
        row = all_rows[i]
        raw_room = normalize(row[col_room]) if col_room < len(row) else ""
        
        if raw_room:
            prev_room_type = _norm_room_kind(raw_room, None)
            room_size = get_room_size(raw_room)
            
            if prev_room_type == target_room:
                # Проверяем пол в комнате и свободные места
                room_gender = None
                free_slots = []
                
                for k in range(room_size):
                    curr_idx = i + k
                    if curr_idx >= len(all_rows):
                        break
                    
                    c_row = all_rows[curr_idx]
                    occupied = is_row_occupied(c_row, col_last, col_first)
                    
                    if occupied:
                        # Определяем пол
                        gen = c_row[col_gender] if col_gender and col_gender < len(c_row) else ""
                        if gen:
                            room_gender = normalize(gen).upper()
                    else:
                        free_slots.append(curr_idx)
                
                # Можем подселить, если пол совпадает или комната пустая
                if free_slots and (room_gender is None or room_gender == gender):
                    # Подселяем людей
                    for slot_idx in free_slots:
                        if people_placed >= group_size:
                            break
                        result_rows.append(slot_idx + 1)
                        all_rows[slot_idx][col_last] = "RESERVED"
                        if col_gender:
                            all_rows[slot_idx][col_gender] = gender
                        people_placed += 1
                        print(f"   ✅ Подселение в строку {slot_idx + 1}")
    
    # Если не все размещены, ищем пустые комнаты
    while people_placed < group_size:
        # 🔥 ИСПРАВЛЕНИЕ: Передаем пол для проверки
        slot = find_empty_room_slot(all_rows, header_row, end_row, cols, target_room, required_gender=gender)
        if not slot:
            print(f"   ❌ Не найдено свободных комнат для пола {gender}")
            return []

        room_size = get_room_size(target_room)
        people_in_room = min(room_size, group_size - people_placed)

        for j in range(people_in_room):
            result_rows.append(slot + j)
            all_rows[slot + j - 1][col_last] = "RESERVED"
            if col_gender:
                all_rows[slot + j - 1][col_gender] = gender
            people_placed += 1
            print(f"   ✅ Новая комната, строка {slot + j}")
    
    return result_rows


def find_empty_room_slot(all_rows, header_row, end_row, cols, target_room, required_gender=None):
    """Поиск полностью пустой комнаты (или комнаты с людьми нужного пола)"""
    col_room = cols.get("room")
    col_last = cols.get("last_name")
    col_gender = cols.get("gender")
    target_room_norm = normalize_room_value(target_room)
    room_capacity = get_room_size(target_room_norm)

    for i in range(header_row + 1, end_row):
        row = all_rows[i]
        raw_room = normalize(row[col_room]) if col_room < len(row) else ""

        if raw_room:
            prev_room_type = _norm_room_kind(raw_room, None)

            if prev_room_type == target_room_norm:
                # Проверяем все места в комнате
                room_genders = set()
                all_empty = True
                has_free_slots = False

                for k in range(room_capacity):
                    curr_idx = i + k
                    if curr_idx >= len(all_rows):
                        break

                    c_row = all_rows[curr_idx]
                    occupied = is_row_occupied(c_row, col_last)

                    if occupied:
                        all_empty = False
                        # Определяем пол
                        gen = c_row[col_gender] if col_gender and col_gender < len(c_row) else ""
                        if gen:
                            room_genders.add(normalize(gen).upper())
                    else:
                        has_free_slots = True

                # Комната подходит если:
                # 1. Полностью пустая
                # 2. ИЛИ в комнате только люди нужного пола (если пол указан) И есть свободные места
                if all_empty:
                    print(f"   🏨 Найдена пустая комната в строке {i + 1}")
                    return i + 1
                elif required_gender and has_free_slots and len(room_genders) == 1 and required_gender in room_genders:
                    # В комнате уже есть люди того же пола И есть свободные места
                    print(f"   🏨 Найдена комната с людьми пола {required_gender} (есть свободные места) в строке {i + 1}")
                    return i + 1

    return None


def find_best_slot(all_rows, target_pkg_name, target_gender, target_room_type):
    """Поиск лучшего места для размещения ОДНОГО человека (обратная совместимость)"""
    print(f"\n{'='*60}")
    print(f"🔍 ПОИСК МЕСТА ДЛЯ РАЗМЕЩЕНИЯ")
    print(f"   Пакет: {target_pkg_name}")
    print(f"   Пол: {target_gender}")
    print(f"   Тип комнаты: {target_room_type}")
    print(f"{'='*60}\n")

    header_row, end_row, cols = get_package_block(all_rows, target_pkg_name)
    if not header_row:
        print("❌ Не удалось найти блок пакета")
        return None, None, "error"

    col_room = cols.get("room")
    col_last = cols.get("last_name")
    col_first = cols.get("first_name")
    col_gender = cols.get("gender")

    if col_room is None or col_last is None:
        print(f"❌ Отсутствуют необходимые колонки: room={col_room}, last_name={col_last}")
        return None, None, "error"

    target_room = normalize_room_value(target_room_type)
    target_gen = normalize(target_gender).upper()
    if target_gen not in ['M', 'F']:
        target_gen = 'M'

    print(f"📊 Диапазон поиска: строки {header_row+1} - {end_row}")
    print(f"🎯 Ищем: {target_room} для пола {target_gen}\n")

    # 1. ПОИСК СВОБОДНОГО МЕСТА (ПОДСЕЛЕНИЕ)
    print("🔍 ШАГ 1: Поиск свободного места в существующих комнатах...")
    fallback_types = ROOM_FALLBACKS.get(target_room, [target_room])
    for room_code in fallback_types:
        require_existing = room_code != target_room
        share_slot = find_share_slot_for_type(
            all_rows, header_row, end_row, cols, room_code, target_gen, require_existing=require_existing
        )
        if share_slot:
            print(f"✅ Найдено свободное место (подселение) в строке {share_slot}")
            return share_slot, cols, "share"

    print("   ❌ Свободных мест для подселения не найдено\n")

    # 2. ПОИСК ВАРИАНТОВ ТРАНСФОРМАЦИИ (как в старой логике)
    print("🔍 ШАГ 2: Поиск возможностей для трансформации...\n")

    # A. Нужен DOUBLE
    if target_room in ['dbl', 'double']:
        print("   Ищем трансформации для DOUBLE:")

        # 1 QUAD -> 2 DOUBLE
        for i in range(header_row + 1, end_row):
            raw = normalize(all_rows[i][col_room]) if col_room < len(all_rows[i]) else ""
            if 'quad' in raw or '4' in raw:
                if check_rows_are_empty(all_rows, i, 4, col_last):
                    print(f"   ✅ Найден пустой QUAD в строке {i+1} (1 QUAD -> 2 DOUBLE)")
                    return i + 1, cols, "trans_1quad_2dbl"

        # 2 TRIPLE -> 3 DOUBLE
        for i in range(header_row + 1, end_row - 3):
            raw1 = normalize(all_rows[i][col_room]) if col_room < len(all_rows[i]) else ""
            if 'trip' in raw1 or 'trpl' in raw1:
                if i + 3 < end_row:
                    raw2 = normalize(all_rows[i+3][col_room]) if col_room < len(all_rows[i+3]) else ""
                    if 'trip' in raw2 or 'trpl' in raw2:
                        if check_rows_are_empty(all_rows, i, 6, col_last):
                            print(f"   ✅ Найдены 2 пустых TRIPLE в строках {i+1} и {i+4} (2 TRIPLE -> 3 DOUBLE)")
                            return i + 1, cols, "trans_2trpl_3dbl"

    # B. Нужен TRIPLE
    elif target_room in ['trpl', 'triple']:
        print("   Ищем трансформации для TRIPLE:")

        # 2 QUAD -> 2 TRIPLE + 1 DOUBLE
        for i in range(header_row + 1, end_row - 4):
            raw1 = normalize(all_rows[i][col_room]) if col_room < len(all_rows[i]) else ""
            if 'quad' in raw1 or '4' in raw1:
                if i + 4 < end_row:
                    raw2 = normalize(all_rows[i+4][col_room]) if col_room < len(all_rows[i+4]) else ""
                    if 'quad' in raw2 or '4' in raw2:
                        if check_rows_are_empty(all_rows, i, 8, col_last):
                            print(f"   ✅ Найдены 2 пустых QUAD в строках {i+1} и {i+5} (2 QUAD -> 2 TRIPLE + DOUBLE)")
                            return i + 1, cols, "trans_2quad_mix"

        # 3 DOUBLE -> 2 TRIPLE
        for i in range(header_row + 1, end_row - 4):
            raw1 = normalize(all_rows[i][col_room]) if col_room < len(all_rows[i]) else ""
            if 'dbl' in raw1 or 'doub' in raw1:
                if i + 2 < end_row:
                    raw2 = normalize(all_rows[i+2][col_room]) if col_room < len(all_rows[i+2]) else ""
                    if 'dbl' in raw2 or 'doub' in raw2:
                        if i + 4 < end_row:
                            raw3 = normalize(all_rows[i+4][col_room]) if col_room < len(all_rows[i+4]) else ""
                            if 'dbl' in raw3 or 'doub' in raw3:
                                if check_rows_are_empty(all_rows, i, 6, col_last):
                                    print(f"   ✅ Найдены 3 пустых DOUBLE (3 DOUBLE -> 2 TRIPLE)")
                                    return i + 1, cols, "trans_3dbl_2trpl"

    # C. Нужен QUADRO
    elif target_room in ['quad', 'quadro']:
        print("   Ищем трансформации для QUADRO:")

        # 2 DOUBLE -> 1 QUAD
        for i in range(header_row + 1, end_row - 2):
            raw1 = normalize(all_rows[i][col_room]) if col_room < len(all_rows[i]) else ""
            if 'dbl' in raw1 or 'doub' in raw1:
                if i + 2 < end_row:
                    raw2 = normalize(all_rows[i+2][col_room]) if col_room < len(all_rows[i+2]) else ""
                    if 'dbl' in raw2 or 'doub' in raw2:
                        if check_rows_are_empty(all_rows, i, 4, col_last):
                            print(f"   ✅ Найдены 2 пустых DOUBLE (2 DOUBLE -> 1 QUAD)")
                            return i + 1, cols, "trans_2dbl_1quad"

    # D. Нужен SINGLE
    elif target_room in ['sing', 'single', 'sgl']:
        print("   Ищем трансформации для SINGLE:")

        # 1 DOUBLE -> 2 SINGLE
        for i in range(header_row + 1, end_row):
            raw = normalize(all_rows[i][col_room]) if col_room < len(all_rows[i]) else ""
            if 'dbl' in raw or 'doub' in raw:
                if check_rows_are_empty(all_rows, i, 2, col_last):
                    print(f"   ✅ Найден пустой DOUBLE (1 DOUBLE -> 2 SINGLE)")
                    return i + 1, cols, "trans_1dbl_2sgl"

        # 1 TRIPLE -> 1 DOUBLE + 1 SINGLE
        for i in range(header_row + 1, end_row):
            raw = normalize(all_rows[i][col_room]) if col_room < len(all_rows[i]) else ""
            if 'trip' in raw or 'trpl' in raw:
                if check_rows_are_empty(all_rows, i, 3, col_last):
                    print(f"   ✅ Найден пустой TRIPLE (1 TRIPLE -> 1 DOUBLE + 1 SINGLE)")
                    return i + 1, cols, "trans_1trpl_mix"

    # 3. ПОИСК ПУСТОЙ КОМНАТЫ
    print("🔍 ШАГ 3: Поиск пустой комнаты...")
    slot = find_empty_room_slot(all_rows, header_row, end_row, cols, target_room)
    if slot:
        print(f"✅ Найдена пустая комната в строке {slot}")
        return slot, cols, "new_room"

    print("❌ Не найдено подходящих мест для размещения\n")
    return None, cols, "no_space"


def get_open_rooms_for_manual_selection(all_rows, pkg_name, needed_count=1, needed_type=None, target_gender=None):
    """Получение списка свободных мест для ручного выбора"""
    print(f"\n{'='*60}")
    print(f"🔍 GET_OPEN_ROOMS вызван:")
    print(f"   Пакет: '{pkg_name}'")
    print(f"   Нужно мест: {needed_count}")
    print(f"   Тип комнаты: '{needed_type}'")
    print(f"   Пол: '{target_gender}'")
    print(f"{'='*60}\n")

    header_row, end_row, cols = get_package_block(all_rows, pkg_name)
    if not header_row:
        print(f"❌ Пакетный блок не найден!")
        return []

    print(f"✅ Блок найден: строки {header_row+1}-{end_row}")
    print(f"   Колонки: {list(cols.keys())}\n")

    col_room = cols.get("room")
    col_last = cols.get("last_name")
    col_first = cols.get("first_name")
    col_gender = cols.get("gender")

    if not all([col_room, col_last]):
        print(f"❌ Не хватает колонок: room={col_room}, last_name={col_last}")
        return []

    rooms_list = []
    target_type_norm = normalize_room_value(needed_type) if needed_type else None
    target_gender_norm = normalize(target_gender).upper() if target_gender else None
    accepted_types = None
    if target_type_norm:
        accepted_types = ROOM_FALLBACKS.get(target_type_norm, [target_type_norm])
    print(f"🎯 Ищем тип: '{target_type_norm}', допускаем: {accepted_types or 'все'}, пол: '{target_gender_norm}'\n")

    i = header_row + 1
    rooms_checked = 0

    while i < end_row and rooms_checked < 100:
        row = all_rows[i]
        raw_room = normalize(row[col_room]) if col_room < len(row) else ""

        if not raw_room:
            i += 1
            continue

        room_type = _norm_room_kind(raw_room, None)
        size = get_room_size(raw_room)
        rooms_checked += 1

        print(f"📍 Строка {i+1}: тип='{room_type}', размер={size}, raw='{raw_room}'")

        if accepted_types and room_type not in accepted_types:
            print(f"   ⏭️  Пропускаем (не подходит по типу)")
            i += size
            continue

        guests: list[str] = []
        genders = set()
        free_count = 0
        first_free_offset = -1

        for k in range(size):
            curr_idx = i + k
            if curr_idx >= end_row:
                break

            c_row = all_rows[curr_idx]
            occupied = is_row_occupied(c_row, col_last, col_first)
            name_val = c_row[col_last] if col_last < len(c_row) else ""
            gen = c_row[col_gender] if col_gender and col_gender < len(c_row) else ""

            if occupied:
                guest_name = name_val.split()[0] if name_val else "Турист"
                guests.append(guest_name)
                if gen:
                    genders.add(normalize(gen).upper())
            else:
                free_count += 1
                if first_free_offset == -1:
                    first_free_offset = k

        is_partially_occupied = len(guests) > 0
        is_completely_empty = (len(guests) == 0 and free_count > 0)
        print(f"   Результат: guests={len(guests)}, free={free_count}, partially_occupied={is_partially_occupied}, completely_empty={is_completely_empty}")

        # Добавляем комнату если есть достаточно свободных мест
        # Для полностью пустой комнаты first_free_offset будет 0 (первая строка комнаты)
        if free_count >= needed_count:
            room_gender = (
                list(genders)[0]
                if len(genders) == 1
                else ("MIX" if len(genders) > 1 else "Empty")
            )

            gender_ok = True
            if target_gender_norm in ['M', 'F']:
                if room_gender in ['M', 'F'] and room_gender != target_gender_norm:
                    gender_ok = False
                elif room_gender == "MIX":
                    gender_ok = False

            if not gender_ok:
                print("   ⏭️  Пропускаем (не подходит по полу)")
                i += size
                continue

            display_guests = ", ".join(guests) if guests else "Свободно"
            last_guest = guests[-1] if guests else "Свободно"
            room_label = f"{room_type.upper()} · {last_guest} (Свободно: {free_count})"

            # Для полностью пустой комнаты начинаем с первой строки (first_free_offset будет 0)
            # Для частично занятой - начинаем с первого свободного места
            actual_offset = 0 if is_completely_empty else first_free_offset

            room_info = {
                'row': i + 1 + actual_offset,
                'type': room_type.title(),
                'guests': display_guests,
                'free': free_count,
                'gender': room_gender if room_gender != "Empty" else (target_gender_norm or 'M'),
                'last_guest': last_guest,
                'label': room_label,
            }
            print(f"   ✅ ДОБАВЛЯЕМ комнату: {room_info}")
            rooms_list.append(room_info)

        i += size

    print(f"\n   ИТОГО найдено комнат: {len(rooms_list)}")
    return rooms_list
