"""
Простой тест логики парсера без зависимостей
"""
import re

# Тестовый текст из EasyOCR
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
print("ТЕСТОВЫЙ ТЕКСТ:")
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

last_name = ""
first_name = ""

print("="*60)
print("ТЕСТИРУЕМ ПАТТЕРНЫ:")
print("="*60)

# Паттерн 1 (ПРИОРИТЕТ): MRZ строка (с учетом пробелов)
print("\n1. Паттерн MRZ строки ([A-Z]{4,})<[\\s<]*([A-Z]{4,}):")
mrz_surname = re.search(r'([A-Z]{4,})<[\s<]*([A-Z]{4,})', test_text)
if mrz_surname:
    surname = mrz_surname.group(1)
    firstname = mrz_surname.group(2)
    print(f"   Найдено: '{surname}' и '{firstname}'")
    if surname not in EXCLUDE_WORDS and firstname not in EXCLUDE_WORDS:
        print(f"   ✅ Проверка пройдена - не служебные слова")
        last_name = surname
        first_name = firstname
    else:
        print(f"   ❌ Отклонено - служебные слова")
else:
    print("   Не найдено")

# Паттерн 2: Узбекские паспорта
if not last_name:
    print("\n2. Паттерн узбекских паспортов (FAMILIYASI/SURNAME):")
    uzb_surname = re.search(r'(?:FAMILIYASI|SURNAME)[^\n]*\n\s*([A-Z]+)', test_text, re.IGNORECASE)
    uzb_firstname = re.search(r'(?:ISMI|GIVEN NAMES)[^\n]*\n\s*([A-Z]+)', test_text, re.IGNORECASE)
    if uzb_surname and uzb_firstname:
        surname = uzb_surname.group(1)
        firstname = uzb_firstname.group(1)
        print(f"   Найдено: '{surname}' и '{firstname}'")
        if surname not in EXCLUDE_WORDS and firstname not in EXCLUDE_WORDS:
            last_name = surname
            first_name = firstname
    else:
        print("   Не найдено")

# Паттерн 3: Обычный текст
if not last_name:
    print("\n3. Паттерн обычного текста (первые 2 латинских слова):")
    lines = test_text.split('\n')
    for i, line in enumerate(lines):
        latin_words = re.findall(r'\b([A-Z]{4,})\b', line)
        latin_words = [w for w in latin_words if w not in EXCLUDE_WORDS]
        if len(latin_words) >= 2:
            print(f"   Строка {i}: '{line}'")
            print(f"   Найдено: {latin_words}")
            last_name = latin_words[0]
            first_name = latin_words[1]
            print(f"   Взяли: '{last_name}' и '{first_name}'")
            break

print("\n" + "="*60)
print("РЕЗУЛЬТАТ:")
print("="*60)
print(f"Фамилия: {last_name}")
print(f"Имя: {first_name}")
print()

if last_name == "SHAKHTAYEVA" and first_name == "KULYAIM":
    print("✅ УСПЕХ! Правильные имена из MRZ строки")
else:
    print(f"❌ ОШИБКА! Получили '{last_name}' и '{first_name}'")
    print(f"   Ожидалось: 'SHAKHTAYEVA' и 'KULYAIM'")
