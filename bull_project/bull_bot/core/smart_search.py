import time
import asyncio
from datetime import datetime
from typing import Dict, List, Tuple

from bull_project.bull_bot.core.google_sheets.client import (
    get_accessible_tables, get_sheet_names, get_packages_from_sheet
)

# -----------------------
# КЭШИ (умные, точечные)
# -----------------------

# 1) Кэш листов по таблице (редко меняется)
SHEETS_CACHE: Dict[str, Tuple[float, List[str]]] = {}
SHEETS_TTL = 60 * 30  # 30 минут

# 2) Кэш результатов по дате (почти realtime)
DATE_CACHE: Dict[str, Tuple[float, List[dict]]] = {}
DATE_TTL = 60  # 60 секунд (можешь поставить 30..120)

def _norm_ddmm(s: str) -> str:
    """Нормализуем ввод: '15/1' -> '15.01', ' 15.01 ' -> '15.01' """
    s = (s or "").strip().replace("/", ".").replace(",", ".")
    parts = s.split(".")
    if len(parts) < 2:
        return s
    dd = parts[0].zfill(2)[:2]
    mm = parts[1].zfill(2)[:2]
    return f"{dd}.{mm}"

async def _get_target_tables_current_next_year() -> Dict[str, str]:
    now = datetime.now()
    years = [str(now.year), str(now.year + 1)]
    all_tables = get_accessible_tables()

    target = {}
    for t_name, t_id in all_tables.items():
        if any(y in t_name for y in years):
            target[t_name] = t_id

    return target

async def _get_sheet_names_cached(table_id: str, force: bool = False) -> List[str]:
    ts, cached = SHEETS_CACHE.get(table_id, (0, []))
    if (not force) and cached and (time.time() - ts < SHEETS_TTL):
        return cached

    names = get_sheet_names(table_id)
    SHEETS_CACHE[table_id] = (time.time(), names or [])
    # маленькая пауза против 429
    await asyncio.sleep(0.3)
    return names or []

async def get_packages_by_date(date_part: str, force: bool = False) -> dict:
    """
    Ищет пакеты ТОЛЬКО по введенной дате DD.MM.
    Возвращает в твоём формате: {found: bool, data: [{d,n,s,t}, ...], error?: str}
    """
    date_part = _norm_ddmm(date_part)

    # Кэш по дате (короткий)
    ts, cached = DATE_CACHE.get(date_part, (0, []))
    if (not force) and cached and (time.time() - ts < DATE_TTL):
        return {"found": True, "data": cached}

    try:
        target_tables = await _get_target_tables_current_next_year()
        if not target_tables:
            return {"found": False, "error": "Нет таблиц текущего/следующего года"}

        collected: List[dict] = []

        for t_name, t_id in target_tables.items():
            try:
                sheet_names = await _get_sheet_names_cached(t_id, force=False)

                # выбираем только листы нужной даты
                # у тебя листы вида "15.01 ..." (это уже в текущем коде проверяется) :contentReference[oaicite:2]{index=2}
                matched = []
                for sheet_name in sheet_names:
                    clean = (sheet_name or "").strip()
                    if len(clean) >= 5 and clean[:5] == date_part:
                        matched.append(sheet_name)

                # если в этой таблице на дату нет листов — идём дальше
                if not matched:
                    continue

                # читаем пакеты только из совпавших листов
                for sheet_name in matched:
                    await asyncio.sleep(0.1)  # микро-пауза
                    packages_map = get_packages_from_sheet(t_id, sheet_name)

                    if not packages_map:
                        continue

                    suffix = (sheet_name or "").replace(date_part, "").strip(" -.|")
                    for _, pkg_name in packages_map.items():
                        display_name = f"{pkg_name} [{suffix}]" if suffix else pkg_name
                        collected.append({
                            "d": date_part,
                            "n": display_name,
                            "s": sheet_name,
                            "t": t_id
                        })

            except Exception as e:
                # не валим весь поиск из-за одной таблицы
                print(f"Ошибка чтения таблицы {t_name}: {e}")
                continue

        if not collected:
            return {"found": False, "error": "Рейсы не найдены."}

        DATE_CACHE[date_part] = (time.time(), collected)
        return {"found": True, "data": collected}

    except Exception as e:
        return {"found": False, "error": str(e)}
