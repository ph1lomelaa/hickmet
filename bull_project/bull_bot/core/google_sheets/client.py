import logging
from gspread.exceptions import WorksheetNotFound
from bull_project.bull_bot.config.settings import get_google_client

logger = logging.getLogger(__name__)

# Простой кэш для списка таблиц, чтобы не ждать 3 секунды при каждом клике
# Он сбросится при перезапуске бота
_tables_cache = None

def get_accessible_tables(use_cache=True) -> dict:
    """
    Возвращает словарь всех доступных таблиц: {"Название": "ID"}
    Использует client.openall(), но только один раз (кэширует результат).
    """
    global _tables_cache

    # Если кэш есть и мы хотим его использовать - возвращаем мгновенно
    if use_cache and _tables_cache:
        return _tables_cache

    client = get_google_client()
    if not client: return {}

    try:
        # Это тяжелый запрос, он занимает 1-3 секунды
        spreadsheets = client.openall()

        result = {}
        for ss in spreadsheets:
            # Можно добавить фильтр по названию, чтобы убрать мусор
            # if "2025" in ss.title:
            result[ss.title] = ss.id

        # Сохраняем в память
        _tables_cache = result
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка получения списка таблиц: {e}")
        return {}

def get_sheet_names(spreadsheet_id: str) -> list:
    """
    Получает список листов (вкладок) по ID таблицы.
    Это быстрый запрос, он НЕ скачивает содержимое ячеек.
    """
    client = get_google_client()
    if not client: return []

    try:
        ss = client.open_by_key(spreadsheet_id)
        # worksheets() загружает только свойства листов (Title, ID), это быстро
        return [ws.title for ws in ss.worksheets()]
    except Exception as e:
        logger.error(f"❌ Ошибка получения листов: {e}")
        return []

def get_packages_from_sheet(spreadsheet_id: str, sheet_name: str) -> dict:
    """
    Скачивает содержимое (пакеты) ТОЛЬКО когда пользователь выбрал лист.
    Оптимизация: скачиваем только колонки A и B (диапазон A1:B200).
    """
    client = get_google_client()
    if not client: return {}

    try:
        ss = client.open_by_key(spreadsheet_id)
        ws = _get_worksheet_by_title(ss, sheet_name)

        # ОПТИМИЗАЦИЯ: Не качаем get_all_values(), качаем только левую часть
        # Это ускоряет процесс в 5-10 раз для широких таблиц
        data = ws.get('A1:B200')

        packages = {}
        keywords = ["niyet", "hikma", "izi", "4u", "premium", "econom", "стандарт", "эконом", "comfort"]

        for idx, row in enumerate(data, start=1):
            if not row: continue

            text_full = " ".join([str(x) for x in row]).lower()

            if any(k in text_full for k in keywords):
                # Берем название из первой непустой ячейки
                raw_name = row[0] if row and row[0] else (row[1] if len(row) > 1 else "Unknown")
                clean_name = str(raw_name).strip().replace("\n", " ")

                if len(clean_name) > 3:
                    packages[idx] = clean_name

        return packages

    except Exception as e:
        logger.error(f"❌ Ошибка поиска пакетов: {e}")
        return {}

def get_sheet_data(sheet_id: str, sheet_name: str):
    """
    Полное скачивание (используется только при записи/Тетрисе).
    Здесь уже придется подождать, но это происходит в фоне.
    """
    client = get_google_client()
    if not client: return []
    try:
        ss = client.open_by_key(sheet_id)
        ws = _get_worksheet_by_title(ss, sheet_name)
        return ws.get_all_values()
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания данных: {e}")
        return []

def _get_worksheet_by_title(spreadsheet, sheet_name: str):
    """
    Пытается найти лист, игнорируя лишние пробелы/регистр.
    """
    normalized = (sheet_name or "").strip()
    if not normalized:
        raise WorksheetNotFound("Sheet name is empty")

    try:
        return spreadsheet.worksheet(normalized)
    except WorksheetNotFound:
        normalized_lower = normalized.lower()
        for ws in spreadsheet.worksheets():
            if ws.title.strip().lower() == normalized_lower:
                return ws
        raise

def get_worksheet_by_title(spreadsheet, sheet_name: str):
    """Публичная обертка для других модулей."""
    return _get_worksheet_by_title(spreadsheet, sheet_name)
