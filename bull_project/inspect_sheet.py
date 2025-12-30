#!/usr/bin/env python3
"""Прямой парсинг мартовского листа"""
import json
import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1uQACMT3jkNHOtzWILUa6HFNnP8V_ll96Terxf5XEzMU"

def get_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    return gspread.authorize(creds)

def main():
    print("="*100)
    print("ПОЛНЫЙ ПАРСИНГ МАРТОВСКОГО ЛИСТА")
    print("="*100)
    
    gc = get_client()
    print(f"\n📂 Открываем таблицу {SPREADSHEET_ID}...")
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    print(f"✅ Таблица: {spreadsheet.title}")
    
    worksheets = spreadsheet.worksheets()
    print(f"\n📋 Листов: {len(worksheets)}")
    for ws in worksheets:
        print(f"   - {ws.title}")
    
    target = None
    for ws in worksheets:
        if ws.title.startswith("07.03"):
            target = ws
            break
    
    if not target:
        print("\n❌ Лист 07.03 не найден!")
        return
    
    print(f"\n✅ Лист: '{target.title}'")
    print(f"\n{'='*100}")
    print("ПЕРВЫЕ 100 СТРОК (A-D):")
    print(f"{'='*100}\n")
    
    data = target.get('A1:D100')
    
    for idx, row in enumerate(data, 1):
        if not row or all(not c.strip() for c in row if c):
            continue
        cells = [f"{chr(65+i)}: {c if c else '-'}" for i, c in enumerate(row)]
        print(f"Строка {idx:3d}: {' | '.join(cells)}")
    
    print(f"\n{'='*100}")
    print("ПОИСК ПАКЕТОВ:")
    print(f"{'='*100}\n")
    
    keywords = ["niyet", "hikma", "izi", "4u", "premium", "econom", "стандарт", "эконом", "comfort", "ramadan", "рамадан", "ramazan", "ramad", "itikaf", "итикаф", "umrah", "умра"]
    found = []
    
    for idx, row in enumerate(data, 1):
        if not row:
            continue
        txt = " ".join(row).lower()
        for kw in keywords:
            if kw in txt:
                found.append((idx, row, kw))
                break
    
    if found:
        print(f"✅ Найдено {len(found)} пакетов:\n")
        for idx, row, kw in found:
            cells = [f"{chr(65+i)}: {c if c else '-'}" for i, c in enumerate(row)]
            print(f"  Строка {idx:3d} ('{kw}'): {' | '.join(cells)}")
    else:
        print("❌ ПАКЕТЫ НЕ НАЙДЕНЫ!")
        print(f"\nКлючи: {', '.join(keywords)}")

if __name__ == "__main__":
    main()
