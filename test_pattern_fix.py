"""
Тест исправленного паттерна MRZ в реальном контексте
"""
import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class PassportData:
    """Данные паспорта"""
    last_name: str = ""
    first_name: str = ""
    dob: str = ""
    gender: str = ""
    document_number: str = ""
    iin: str = ""
    is_valid: bool = False

# Тестовый текст из EasyOCR (как будет в реальном боте)
test_text = """1из
ПАСПОРТ IPASSPORT
татом
661109450217
Uulll55
КАЧАДСАН
06.09.2032
MILIRY CF INTERNAL AFTARS
<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
SHAKHTAYEVA< <KULYAIM< <<<<<<<<<<<<<<<<<<<<<
<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"""

print("="*60)
print("ТЕСТОВЫЙ ТЕКСТ (из EasyOCR):")
print("="*60)
print(test_text)
print("\n")

# Служебные слова
EXCLUDE_WORDS = {
    'TYPI', 'TYPE', 'PASSPORT', 'CODE', 'STATE', 'GIVEN', 'NAMES',
    'GIVENNAMES', 'DATE', 'BIRTH', 'PLACE', 'ISSUE', 'EXPIRY',
    'AUTHORITY', 'MINISTRY', 'INTERNAL', 'AFFAIRS', 'KAZAKHSTAN',
    'КАЗАХСТАН', 'ПАСПОРТ', 'DATEOFBIRTH', 'PLACEOFBIRTH',
    'DATEOFISSUE', 'DATEOFEXPIRY', 'AUHORIY', 'CODEOFSTATE'
}

data = PassportData()

print("="*60)
print("ПРИМЕНЯЕМ ЛОГИКУ ПАРСЕРА (passport_parser.py:392-413):")
print("="*60)

# Паттерн 1 (ПРИОРИТЕТ): MRZ строка (самый надежный источник, с учетом пробелов)
print("\n1. Паттерн MRZ строки: ([A-Z]{4,})<[\\s<]*([A-Z]{4,})")
mrz_surname = re.search(r'([A-Z]{4,})<[\s<]*([A-Z]{4,})', test_text)
if mrz_surname:
    surname = mrz_surname.group(1)
    firstname = mrz_surname.group(2)
    print(f"   Найдено: '{surname}' и '{firstname}'")
    # Проверяем, что это не мусор
    if surname not in EXCLUDE_WORDS and firstname not in EXCLUDE_WORDS:
        data.last_name = surname
        data.first_name = firstname
        print(f"   ✅ Проверка пройдена - не служебные слова")
        print(f"   Установлено: last_name='{data.last_name}', first_name='{data.first_name}'")
    else:
        print(f"   ❌ Отклонено - служебные слова")
else:
    print("   Не найдено")

# Паттерн 2: Узбекские паспорта (FAMILIYASI/SURNAME, ISMI/GIVEN NAMES)
if not data.last_name:
    print("\n2. Паттерн узбекских паспортов (не применяется - уже нашли)")
else:
    print("\n2. Паттерн узбекских паспортов (пропущен - уже нашли в MRZ)")

# Паттерн 3: Обычный текст (последний приоритет)
if not data.last_name:
    print("\n3. Паттерн обычного текста (не применяется - уже нашли)")
else:
    print("\n3. Паттерн обычного текста (пропущен - уже нашли в MRZ)")

print("\n" + "="*60)
print("РЕЗУЛЬТАТ:")
print("="*60)
print(f"Фамилия: {data.last_name}")
print(f"Имя: {data.first_name}")
print()

if data.last_name == "SHAKHTAYEVA" and data.first_name == "KULYAIM":
    print("✅ УСПЕХ! Исправленный паттерн работает правильно")
    print("   MRZ строка обработана корректно (с учетом пробелов)")
else:
    print(f"❌ ОШИБКА! Получили '{data.last_name}' и '{data.first_name}'")
    print(f"   Ожидалось: 'SHAKHTAYEVA' и 'KULYAIM'")
