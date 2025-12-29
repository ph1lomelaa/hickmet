"""
Утилита: выводит первые 200 строк первого листа Google Sheets
с базовым форматированием (цвет фона, формат числа, отображаемое значение).

Запуск:
  python inspect_sheet.py --sheet-id <ID> [--credentials path/to/service_account.json]

Требования:
  pip install google-api-python-client google-auth
  (gspread в проекте уже тянет google-auth, но клиент может отсутствовать)
"""

import argparse
import sys
from typing import Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


def color_to_hex(color: Optional[dict]) -> str:
    """Конвертирует цвет Google API в HEX."""
    if not color:
        return "#FFFFFF"
    r = int(color.get("red", 1) * 255)
    g = int(color.get("green", 1) * 255)
    b = int(color.get("blue", 1) * 255)
    return f"#{r:02X}{g:02X}{b:02X}"


def main():
    parser = argparse.ArgumentParser(description="Показать первые 200 строк первого листа")
    parser.add_argument("--sheet-id", required=True, help="ID таблицы (длинная строка из URL)")
    parser.add_argument(
        "--credentials",
        default="bull_bot/credentials/service_account.json",
        help="Путь к service_account.json (по умолчанию bull_bot/credentials/service_account.json)",
    )
    args = parser.parse_args()

    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    try:
        creds = Credentials.from_service_account_file(args.credentials, scopes=scopes)
    except Exception as e:
        sys.stderr.write(f"❌ Не удалось загрузить креды: {e}\n")
        sys.exit(1)

    service = build("sheets", "v4", credentials=creds)

    # Узнаем имя первого листа
    meta = service.spreadsheets().get(
        spreadsheetId=args.sheet_id,
        fields="sheets(properties(title))",
    ).execute()
    first_title = meta["sheets"][0]["properties"]["title"]

    # Берем первые 200 строк (A:Z можно расширить при необходимости)
    rng = f"{first_title}!A1:Z200"
    resp = service.spreadsheets().get(
        spreadsheetId=args.sheet_id,
        ranges=[rng],
        includeGridData=True,
        fields="sheets(data(rowData(values(formattedValue,effectiveFormat(backgroundColor,textFormat,numberFormat)))))",
    ).execute()

    data = resp["sheets"][0]["data"][0].get("rowData", [])
    for i, row in enumerate(data, start=1):
        cells = row.get("values", [])
        pretty_cells = []
        for cell in cells:
            val = cell.get("formattedValue", "")
            fmt = cell.get("effectiveFormat", {}) or {}
            bg = color_to_hex(fmt.get("backgroundColor"))
            num_fmt = fmt.get("numberFormat", {})
            fmt_str = num_fmt.get("pattern") or num_fmt.get("type") or ""
            pretty_cells.append(f"[{val} | {bg} | {fmt_str}]")
        print(f"{i:03d}: " + " ".join(pretty_cells))


if __name__ == "__main__":
    main()
