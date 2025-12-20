
import re
from datetime import datetime

CITY_ALIASES = {
    "madinah": ["madinah", "medinah", "medina", "madina", "mdinah", "mdina", "мадина", "медина"],
    "makkah":  ["makkah", "makka", "mecca", "mekka", "makah", "макка", "мекка"],
}
PKG_KIND_ALIASES = {
    # сначала более специфичные
    "niyet/10d": [
        "niyet/10d", "niyet 10d", "niyet 10 days", "niyet /10 d"
    ],
    "niyet/7d": [
        "niyet/7d", "niyet 7 days"
    ],

    # базовый NIYET
    "niyet": [
        "niyet", "ниет", "niyet economy", "niyet econom",
        "акцион", "акция", "акционный", "akcion"
    ],

    # HIKMA
    "hikma": ["hikma", "хикма"],

    # IZI / 4 YOU / AMAL / 4U
    "izi": [
        "izi", "izi swissotel", "izi fairmont",
        "izi 4u", "izi 4 u", "izi 4 you",
        "4 you", "4you", "4u", "4 u",
        "swiss/4 you", "4 you shohada",
        "aa 4 u", "aa4u",
        "amal", "амал"
    ],

    # AROYA
    "aroya": ["aroya", "ароя", "arоya", "aroya only"],

    # AA
    "aa": ["aa", "aa/7days", "aa/7 days"],

    # прочие
    "shohada": ["shohada"],
    "aktau": ["aktau"],
    "nqz": ["nqz"],
    "sco-med": ["sco-med", "sco med"],
    "ala-jed": ["ala-jed", "ala-med", "jed-med", "med-jed", "med-mak", "mak-med"],
    "standard": ["standard"],
}


def find_palm_packages(ws) -> list[dict]:
    """
    Ищет «шапки» пакетов на листе паломников.
    Возвращает список словарей: {'title': str, 'row': int, 'col': int}
    """
    data = ws.get_all_values()
    H = len(data)
    found = []

    for r in range(H):
        row = data[r]
        for c, raw in enumerate(row):
            txt = normtxt(str(raw))
            if not txt:
                continue
            # ищем диапазон дат в заголовке пакета
            if RANGE_RE.search(txt):
                # подтверждаем, что ниже действительно начинается таблица с колонками
                header_nearby = False
                for k in range(1, 6):  # смотрим 1..5 строк ниже
                    rr = r + k
                    if rr < H and row_has_table_header(data[rr]):
                        header_nearby = True
                        break
                if not header_nearby:
                    continue

                found.append({"title": txt, "row": r, "col": c})
                break  # на этой строке уже нашли один заголовок

    # убираем дубликаты и сортируем по порядку сверху-вниз
    uniq, seen = [], set()
    for item in sorted(found, key=lambda x: x["row"]):
        key = normtxt(item["title"]).lower()
        if key not in seen:
            seen.add(key)
            uniq.append(item)
    return uniq
def row_has_any(row, keywords: tuple[str, ...]) -> bool:
    """Проверяет, содержит ли строка любые из ключевых слов"""
    line = low(' '.join(row))
    return any(k in line for k in keywords)

def find_config_block(data: list[list[str]], start_r: int, end_r: int, want_kind: str) -> tuple[int | None, dict]:
    """
    Универсальный поиск конфигурации отелей:
    1) Ищем строки, где встречаются алиасы пакета (HIKMA / IZI / 4U / NIYET / AMAL / AA 4 U и т.д.)
    2) Вокруг найденной строки (текущая + 4 ниже) ищем строки с Madinah/Makkah
    3) Если нашли обе – формируем payload
    Возвращает:
      - абсолютный индекс строки конфига (int) или None
      - payload (dict)
    """
    want_kind = (want_kind or "niyet").lower()
    want_words = tuple(PKG_KIND_ALIASES.get(want_kind, PKG_KIND_ALIASES["niyet"]))

    print(f"🔍 Поиск конфигурации для типа '{want_kind}' в диапазоне {start_r}-{end_r}")
    print(f"🔍 Ключевые слова: {want_words}")

    H = len(data)
    mad = {"hotel": None, "when": None}
    mak = {"hotel": None, "when": None}

    def _nights_from_when(when: str) -> int | None:
        if not when:
            return None
        parts = [p.strip() for p in when.split("–")]
        if len(parts) != 2:
            return None
        return nights(parts[0], parts[1])

    # Ищем строки с ключевыми словами пакета ПО ВСЕМУ ЛИСТУ, начиная со start_r
    for r in range(start_r, H):
        row = data[r]
        if not row_has_any(row, want_words):
            continue

        print(f"🔍 Найдена строка с ключевыми словами в R{r+1}: {row}")

        # смотрим текущую и 4 следующие строки на наличие городов
        for rr in range(r, min(r + 5, H)):
            rw = data[rr]

            # Ищем Медина + отель + даты
            h, w = extract_city_line(rw, "madinah")
            if h and not mad["hotel"]:
                mad["hotel"] = h
                print(f"📍 Найдена Медина: {h}")
            if w and not mad["when"]:
                mad["when"] = w
                print(f"📅 Даты Медины: {w}")

            # Ищем Мекка + отель + даты
            h, w = extract_city_line(rw, "makkah")
            if h and not mak["hotel"]:
                mak["hotel"] = h
                print(f"📍 Найдена Мекка: {h}")
            if w and not mak["when"]:
                mak["when"] = w
                print(f"📅 Даты Мекки: {w}")

            # Если нашли обе конфигурации - формируем payload
            if mad["hotel"] and mad["when"] and mak["hotel"] and mak["when"]:
                s1 = _nights_from_when(mad["when"])
                s2 = _nights_from_when(mak["when"])

                payload = {
                    "city1": "Madinah",
                    "hotel1": mad["hotel"],
                    "dates1": mad["when"],
                    "checkin1": "16:00",
                    "stay1": s1,
                    "stay1_nights": s1,

                    "city2": "Makkah",
                    "hotel2": mak["hotel"],
                    "dates2": mak["when"],
                    "checkin2": "16:00",
                    "stay2": s2,
                    "stay2_nights": s2,

                    "service": "Виза и страховка",
                    "meal": "Завтрак и ужин",
                    "guide": "Групповой гид",
                    "excursions": "Мекка, Медина",
                    "tech_guide": "+966 56 328 0325",
                    "transfer": "—",
                }

                print(f"✅ Конфигурация найдена в строке {rr+1}")
                # ВОЗВРАЩАЕМ АБСОЛЮТНЫЙ ИНДЕКС
                return rr, payload

    print("❌ Конфигурация не найдена в указанном диапазоне")
    return None, {}


def find_config_block_by_package_name(
        data: list[list[str]],
        start_r: int,
        end_r: int,
        package_title: str,
) -> tuple[int | None, dict]:
    """
    Универсальный поиск конфигурации отелей по названию пакета.
    Сейчас основное применение — 4U-пакеты (Shohada / Swiss / Fairmont).
    Для 4U вызываем отдельный алгоритм, для остальных — более общий fallback.
    """
    title_lower = str(package_title).lower()

    # 1) Специальный путь для 4U
    if "4u" in title_lower or "4 u" in title_lower:
        return find_config_block_4u(data, package_title)

    # 2) Fallback для нестандартных кейсов
    H = len(data)
    print(f"🔍 Поиск конфигурации для пакета: '{package_title}' (общий fallback)")

    # **НОВОЕ**: вытаскиваем первый день тура из title
    start_ddmm = first_ddmm_from_title(package_title)
    if start_ddmm:
        print(f"📌 Фильтр по стартовой дате тура: {start_ddmm}")

    search_start = max(0, H - 40)
    madinah_found = None
    makkah_found = None

    for r in range(search_start, H):
        row = data[r]
        city, hotel, d1, d2 = extract_city_line_simple(row)
        if not city or not d1 or not d2:
            continue

        # **НОВОЕ**: если есть стартовая дата, берём только те конфиги,
        # у которых заезд в первый город начинается в тот же день-месяц.
        # d1 в формате 'dd/mm/yyyy' -> берём первые 5 символов 'dd/mm'
        if start_ddmm and d1[:5] != start_ddmm:
            continue

        if city == "Madinah" and not madinah_found:
            madinah_found = {
                "city": city,
                "hotel": hotel or "—",
                "d1": d1,
                "d2": d2,
                "row": r,
            }
        elif city == "Makkah" and not makkah_found:
            makkah_found = {
                "city": city,
                "hotel": hotel or "—",
                "d1": d1,
                "d2": d2,
                "row": r,
            }

        if madinah_found and makkah_found:
            break

    # дальше всё как у тебя
    if not madinah_found or not makkah_found:
        print("❌ (fallback) Не нашли полную конфигурацию (Madinah + Makkah)")
        return None, {}

    s1 = nights(madinah_found["d1"], madinah_found["d2"])
    s2 = nights(makkah_found["d1"], makkah_found["d2"])

    payload = {
        "city1": madinah_found["city"],
        "hotel1": madinah_found["hotel"],
        "dates1": f"{madinah_found['d1']} – {madinah_found['d2']}",
        "checkin1": "16:00",
        "stay1": s1,
        "stay1_nights": s1,

        "city2": makkah_found["city"],
        "hotel2": makkah_found["hotel"],
        "dates2": f"{makkah_found['d1']} – {makkah_found['d2']}",
        "checkin2": "16:00",
        "stay2": s2,
        "stay2_nights": s2,

        "service": "Виза и страховка",
        "meal": "Завтрак и ужин",
        "guide": "Групповой гид",
        "excursions": "Мекка, Медина",
        "transfer": "Автобус",
    }

    cfg_row = min(madinah_found["row"], makkah_found["row"])
    print(f"✅ (fallback) Конфигурация найдена в строках {madinah_found['row']+1} и {makkah_found['row']+1}")
    return cfg_row, payload



def find_config_block_4u(data: list[list[str]], package_title: str) -> tuple[int | None, dict]:
    """
    Специальный поиск конфигурации отелей ДЛЯ 4U-пакетов:
    - бегаем по нижней части листа (конфиги SHOHADA / SWISS / FAIRMONT)
    - для Madinah берём последнюю строку перед нужной Makkah
    - для Makkah фильтруем по hotel_kw из названия пакета
    """
    H = len(data)
    hotel_kw = hotel_kw_from_4u_title(package_title)
    start_ddmm = first_ddmm_from_title(package_title)
    print(f"🔍 [4U] Поиск конфига для '{package_title}', hotel_kw={hotel_kw!r}, start_ddmm={start_ddmm!r}")

    start_row = max(0, H - 40)
    last_madinah = None

    for r in range(start_row, H):
        row = data[r]
        city, hotel, d1, d2 = extract_city_line_simple(row)
        if not city or not d1 or not d2:
            continue

        row_text = " ".join(norm_spaces(c) for c in row if norm_spaces(c))
        row_low = row_text.lower()

        if city == "Madinah":
            # если указан первый день тура — игнорируем чужие даты
            if start_ddmm and d1[:5] != start_ddmm:
                continue

            last_madinah = {
                "city": city,
                "hotel": hotel or "—",
                "d1": d1,
                "d2": d2,
                "row": r,
            }
            print(f"📍 [4U] Madinah row R{r+1}: {row_text}")

        elif city == "Makkah":
            if hotel_kw and hotel_kw not in row_low:
                continue

            print(f"📍 [4U] Makkah row R{r+1}: {row_text}")

            if not last_madinah:
                continue

            mad = last_madinah

            s1 = nights(mad["d1"], mad["d2"])
            s2 = nights(d1, d2)

            payload = {
                "city1": mad["city"],
                "hotel1": mad["hotel"],
                "dates1": f"{mad['d1']} – {mad['d2']}",
                "checkin1": "16:00",
                "stay1": s1,
                "stay1_nights": s1,

                "city2": city,
                "hotel2": hotel or "—",
                "dates2": f"{d1} – {d2}",
                "checkin2": "16:00",
                "stay2": s2,
                "stay2_nights": s2,

                "service": "Виза и страховка",
                "meal": "Завтрак и ужин",
                "guide": "Групповой гид",
                "excursions": "Мекка, Медина",
                "transfer": "Автобус",
                "tech_guide": "+966 56 328 0325",
            }

            cfg_row = min(mad["row"], r)
            print(f"✅ [4U] Конфигурация найдена: Madinah={mad['hotel']} / Makkah={hotel or '—'} (строки {mad['row']+1} и {r+1})")
            return cfg_row, payload

    print("❌ [4U] Не удалось найти конфиг для 4U-пакета по названию")
    return None, {}

def debug_show_config_area(data: list[list[str]], start_row: int, num_rows: int = 10):
    """Показывает область данных для отладки конфигурации"""
    print(f"\n=== ОТЛАДКА КОНФИГУРАЦИИ (строки {start_row}-{start_row+num_rows}) ===")
    for r in range(start_row, min(start_row + num_rows, len(data))):
        row = data[r]
        non_empty = [f"{i}:{repr(str(cell).strip())}" for i, cell in enumerate(row) if str(cell).strip()]
        if non_empty:
            print(f"R{r+1}: {non_empty}")




def nights(d1: str, d2: str) -> int|None:
    """Вычисляет количество ночей между двумя датами"""
    try:
        a = datetime.strptime(d1, "%d/%m/%Y")
        b = datetime.strptime(d2, "%d/%m/%Y")
        return max(0, (b - a).days)
    except Exception:
        return None

def extract_city_line_simple(row):
    def clean(x):
        return norm_spaces(str(x) or "")

    # Берем только непустые ячейки
    parts = [clean(x) for x in row if clean(x)]
    if not parts:
        return None, None, None, None

    # 1) Определяем город
    city = None
    for part in parts:
        low_part = part.lower()
        if any(name in low_part for name in CITY_ALIASES["madinah"]):
            city = "Madinah"
            break
        if any(name in low_part for name in CITY_ALIASES["makkah"]):
            city = "Makkah"
            break

    if not city:
        return None, None, None, None

    # 2) Ищем 2 даты через DATE_ANY (поддерживает и . и /)
    dates = []

    for part in parts:
        for dd, mm, yy in DATE_ANY.findall(part):
            yy = ("20" + yy) if len(yy) == 2 else yy
            dates.append(f"{dd.zfill(2)}/{mm.zfill(2)}/{yy}")
            if len(dates) >= 2:
                break
        if len(dates) >= 2:
            break

    if len(dates) < 2:
        return city, None, None, None

    d1, d2 = dates[0], dates[1]

    # 3) Отель — первый элемент ПОСЛЕ города, который не является датой
    hotel = None
    seen_city = False
    for part in parts:
        low_part = part.lower()

        if not seen_city:
            # Ждём, пока встретим город, чтобы после него ловить отель
            if any(name in low_part for name in CITY_ALIASES["madinah"] + CITY_ALIASES["makkah"]):
                seen_city = True
            continue

        # Уже после города: пропускаем даты
        if DATE_ANY.search(part):
            continue

        hotel = part
        break

    return city, hotel, d1, d2


def package_bounds(ws, pkg_row: int) -> tuple[int, int, list[dict]]:
    """Границы выбранного пакета [start, next) и список всех пакетов на листе"""
    all_pk = find_palm_packages(ws)
    H = len(ws.get_all_values())
    nxt = H
    for p in all_pk:
        if p["row"] > pkg_row:
            nxt = p["row"]
            break
    return pkg_row, nxt, all_pk

def kind_from_title(title: str) -> str:
    t = low(str(title))
    for canon, variants in PKG_KIND_ALIASES.items():
        if any(v in t for v in variants):
            return canon
    return "niyet"

def first_ddmm_from_title(title: str) -> str | None:

    m = DATE_ANY.findall(str(title))
    if not m:
        return None
    dd, mm, yy = m[0]
    return f"{dd.zfill(2)}/{mm.zfill(2)}"

def extract_city_line(row, city_key: str) -> tuple[str|None, str|None]:
    """Из одной строки пробуем достать hotel + две даты"""
    aliases = CITY_ALIASES[city_key]

    for c, cell in enumerate(row):
        lc = low(cell)
        if any(a in lc for a in aliases):
            hotel = hotel_to_right(row, c) or None
            d1, d2 = two_dates_from_cells(row[c:c+8])
            when = f"{d1} – {d2}" if d1 and d2 else None
            return hotel, when
    return None, None

def hotel_to_right(row, city_col: int) -> str:
    """Ищет отель справа от города"""
    for j in range(city_col + 1, len(row)):
        v = norm_spaces(row[j])
        if v:
            return v
    return ""

# Вспомогательные функции
def low(s: str) -> str:
    return re.sub(r'[\s\u00A0\u202F]+', ' ', (str(s) or '')).strip().lower()

def norm_spaces(s: str) -> str:
    return re.sub(r'[\s\u00A0\u202F]+', ' ', (str(s) or '')).strip()

def to_slash(d: str) -> str:
    return d.replace('.', '/')

def two_dates_from_cells(cells) -> tuple[str|None, str|None]:
    """Извлекает две даты из ячеек"""
    txt = ' '.join(norm_spaces(str(x)) for x in cells)
    m = DATE_ANY.findall(txt)
    if len(m) >= 2:
        def build(t):
            dd, mm, yy = t
            yy = ('20'+yy) if len(yy) == 2 else yy
            return to_slash(f"{dd.zfill(2)}/{mm.zfill(2)}/{yy}")
        return build(m[0]), build(m[1])
    return None, None

def normtxt(s: str) -> str:
    """Нормализация текста"""
    return norm_spaces(str(s))

def row_has_table_header(row) -> bool:
    """Проверяет, содержит ли строка заголовок таблицы"""
    header_keywords = ['name', 'names', 'фио', 'паломник', 'pilgrim', 'room', 'комната']
    row_text = ' '.join(str(cell) for cell in row).lower()
    return any(keyword in row_text for keyword in header_keywords)

def is_4u_title(title: str) -> bool:
    t = low(str(title))
    return "4u" in t or "4 u" in t


def hotel_kw_from_4u_title(title: str) -> str | None:
    """
    Из названия пакета вида:
      '15.11-19.11/4U SHOHADA'
      '15.11-19.11 / 4U SWISS'
      '15.11-26.11/4U fairmont'
    вытаскиваем ключевое слово отеля: shohada / swiss / fairmont и т.п.
    """
    t = low(str(title))

    # Пытаемся поймать слово после "4u"
    m = re.search(r"4\s*u[ /]+([a-zа-яё0-9]+)", t)
    if m:
        return m.group(1).strip()

    # Fallback — просто смотрим самые частые бренды
    for kw in ["shohada", "swissotel", "swiss", "fairmont", "address", "rixos"]:
        if kw in t:
            return kw

    return None


# Добавьте недостающие константы если нужно
RANGE_RE = re.compile(r'\d{1,2}\.\d{1,2}\s*[-–]\s*\d{1,2}\.\d{1,2}')
DATE_ANY = re.compile(r'(\d{1,2})[./](\d{1,2})[./](\d{2,4})')
# Заполните алиасами типов пакетов