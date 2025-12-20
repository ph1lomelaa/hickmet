import re

# ==================== ЗАЩИТА ОТ ОШИБОК ИМПОРТА ====================
# Мы определяем списки ПРЯМО ЗДЕСЬ, чтобы файл работал автономно

HOTELS_NAME_HINTS = [
    "hotel", "otel", "отель", "гостиница",
    "makkah", "madinah", "mekka", "medina", "мекка", "медина",
    "shohada", "swiss", "fairmont", "pullman", "zamzam",
    "movempick", "hilton", "conrad", "jabal", "omar",
    "anwar", "dar", "iman", "taiba", "aram", "millennium",
    "front", "view", "city", "tower", "voco", "sheraton",
    "address", "convention", "jumeirah", "marriott",
    "courtyard", "vally", "wof", "sfi"
]

NOISE_TOKENS = [
    "inf", "chd", "child", "baby", "infant", "инфант", "ребенок",
    "no visa", "visa", "ticket", "guide", "гид",
    "total", "price", "room", "dbl", "trpl", "quad", "quin",
    "paid", "free", "cancel", "change", "adult", "pax",
    "sum", "итог", "всего", "transfer", "train", "bus"
]

DATE_TOKEN_RX = re.compile(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}')

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def _norm_spaces(s: str) -> str:
    """Убирает лишние пробелы"""
    if not s: return ""
    return re.sub(r'\s+', ' ', str(s)).strip()

def is_valid_name(s: str) -> bool:
    """Проверка: похоже ли это на имя?"""
    if not s or len(s) < 2: return False
    # Если есть цифры — это точно не имя
    if re.search(r'\d', s): return False
    return True

def _build_bad_name_sets():
    """Строит списки слов-исключений"""
    exact = set()
    contains = set()

    # Теперь это безопасно, так как список HOTELS_NAME_HINTS определен выше
    for word in HOTELS_NAME_HINTS:
        contains.add(word.lower())

    for token in ["room", "dbl", "trpl", "quad", "quin", "total", "price"]:
        exact.add(token)

    return exact, contains

# Инициализируем фильтры
BAD_FIO_EXACT, BAD_FIO_CONTAINS = _build_bad_name_sets()

def is_hotel_or_header_row(row: list[str]) -> bool:
    """Проверяет, является ли строка названием отеля или заголовком"""
    text = " ".join([str(x) for x in row]).lower()

    for h in HOTELS_NAME_HINTS:
        if h in text: return True

    if "total" in text or "price" in text: return True
    return False

# Функции для безопасного извлечения данных из колонок
def get_last(row, cols):   return _norm_spaces(row[cols["last"]])  if "last"  in cols and cols["last"]  < len(row) else ""
def get_first(row, cols):  return _norm_spaces(row[cols["first"]]) if "first" in cols and cols["first"] < len(row) else ""
def get_meal(row, cols):   return _norm_spaces(row[cols["meal"]])  if "meal"  in cols and cols["meal"]  < len(row) else ""
def get_room(row, cols):   return _norm_spaces(row[cols["room"]])  if "room"  in cols and cols["room"]  < len(row) else ""

def detect_people_header(row: list[str]) -> dict | None:
    """
    Ищет заголовки колонок (Фамилия, Имя, Пол...) в строке.
    Возвращает словарь индексов: {'last': 4, 'gender': 6 ...}
    """
    row_lower = [str(c).lower().strip() for c in row]
    row_text = " ".join(row_lower)

    # Быстрая проверка: есть ли тут вообще намек на заголовки?
    has_name = any(x in row_text for x in ['name', 'фио', 'surname', 'last name', 'first name'])
    has_room_or_gender = any(x in row_text for x in ['room', 'gender', 'sex', 'пол', 'комната'])

    if not (has_name and has_room_or_gender):
        return None

    cols = {}

    # Карта поиска ключевых слов
    KEYWORD_MAP = {
        "last": ["last name", "lastname", "surname", "фамилия"],
        "first": ["first name", "firstname", "name", "имя"],
        "gender": ["gender", "sex", "пол"],
        "room": ["type of room", "room", "комната", "тип"],
        "meal": ["meal", "питание", "food"],
        "visa": ["visa", "виза"],
        "price": ["price", "цена", "стоимость"],
        "dob": ["date of birth", "dob", "дата рождения", "д.р."],
        "doc_num": ["document number", "passport", "номер паспорта", "№"],
        "doc_exp": ["document expiration", "expiry", "срок действия", "годен до"],
        "manager": ["manager", "менеджер"],
        "comment": ["comment", "комментарий", "примечание"],
        "avia": ["avia", "авиа", "рейс", "flight"],
        "train": ["train", "поезд"]
    }

    for idx, val in enumerate(row_lower):
        if not val: continue
        for key, keywords in KEYWORD_MAP.items():
            # Если колонка еще не найдена и слово подходит
            if key not in cols and any(k in val for k in keywords):
                cols[key] = idx

    # Проверка: нашли ли мы минимум для работы?
    if ("last" in cols or "first" in cols) and ("room" in cols or "gender" in cols):
        return cols

    return None

def _norm_room_kind(s: str, prev: str|None) -> str|None:
    """
    Нормализует тип комнаты (QUAD -> quad).
    Если ячейка пустая (объединенная), берет значение из prev (предыдущей строки).
    """
    if not s: return prev

    t = s.lower().strip()

    # 🔥 ОТЛАДКА: выводим что пришло
    print(f"🔍 _norm_room_kind вызвана с: '{s}' -> после lower: '{t}'")

    if "quad" in t or "4" in t:
        print(f"   ✅ Распознано как QUAD")
        return "quad"
    if "trip" in t or "trpl" in t or "3" in t:
        print(f"   ✅ Распознано как TRIPLE")
        return "trpl"
    if "doub" in t or "dbl" in t or "2" in t:
        print(f"   ✅ Распознано как DOUBLE")
        return "dbl"
    if "sing" in t or "sgl" in t or "1" in t:
        print(f"   ✅ Распознано как SINGLE")
        return "sgl"
    if "quin" in t or "5" in t:
        print(f"   ✅ Распознано как QUIN")
        return "quin"
    if "inf" in t:
        print(f"   ✅ Распознано как INFANT")
        return "inf"

    print(f"   ❌ НЕ распознано, возвращаем prev={prev}")
    return prev

def norm_hdr(s: str) -> str:
    if s is None: return ""
    s = str(s).replace("\xa0", " ").replace("\u202f", " ").lower().strip()
    return re.sub(r"\s+", " ", s)