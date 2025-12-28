"""
Тест всех случаев MRZ паттерна
"""
import re

EXCLUDE_WORDS = {
    'TYPI', 'TYPE', 'PASSPORT', 'CODE', 'STATE', 'GIVEN', 'NAMES',
    'GIVENNAMES', 'DATE', 'BIRTH', 'PLACE', 'ISSUE', 'EXPIRY',
    'AUTHORITY', 'MINISTRY', 'INTERNAL', 'AFFAIRS', 'KAZAKHSTAN',
    'КАЗАХСТАН', 'ПАСПОРТ', 'DATEOFBIRTH', 'PLACEOFBIRTH',
    'DATEOFISSUE', 'DATEOFEXPIRY', 'AUHORIY', 'CODEOFSTATE'
}

def test_mrz(mrz_line, expected_surname, expected_firstname, case_name):
    print(f"\n{'='*60}")
    print(f"ТЕСТ: {case_name}")
    print(f"{'='*60}")
    print(f"MRZ: {mrz_line}")

    # Попытка 1: Полная MRZ с префиксом P<CCC
    mrz_surname = re.search(r'P\s*<\s*[A-Z]{3}\s*<?\s*([A-Z\s<]+?)<<\s*([A-Z]+)', mrz_line)

    # Попытка 2: Запасной паттерн без префикса
    if not mrz_surname:
        mrz_surname = re.search(r'([A-Z]{4,})<[\s<]*([A-Z]{4,})', mrz_line)

    if mrz_surname:
        surname_raw = mrz_surname.group(1)
        firstname = mrz_surname.group(2)
        surname = re.sub(r'[<\s]+', ' ', surname_raw).strip()

        print(f"✅ Распознано: Фамилия='{surname}', Имя='{firstname}'")

        if surname == expected_surname and firstname == expected_firstname:
            print(f"✅ УСПЕХ!")
            return True
        else:
            print(f"❌ ОШИБКА!")
            print(f"   Ожидалось: Фамилия='{expected_surname}', Имя='{expected_firstname}'")
            return False
    else:
        print(f"❌ Паттерн не нашел совпадение")
        return False

# Тест 1: Казахский паспорт (оригинальный)
test_mrz(
    "P<KAZNASSIPKHAN<<TOLEU<<<<<<<<<<<<<<<<<<<<<<",
    "NASSIPKHAN", "TOLEU",
    "Казахский паспорт (без пробелов)"
)

# Тест 2: Узбекский паспорт (оригинальный)
test_mrz(
    "P<UZBKUANBAEVA<<RAYA <ALTYBAEVNA <<<<<<<<<<<< <",
    "KUANBAEVA", "RAYA",
    "Узбекский паспорт (с пробелами после имени)"
)

# Тест 3: Казахский паспорт с пробелами в фамилии
test_mrz(
    "P <KAZAKHME J ANOV<<KENES<<<<<<<<<<<<<<<<<<<<< <",
    "AKHME J ANOV", "KENES",
    "Казахский паспорт (фамилия с пробелами и OCR артефактами)"
)

# Тест 4: Первый тестовый случай
test_mrz(
    "SHAKHTAYEVA< <KULYAIM< <<<<<<<<<<<<<<<<<<<<<",
    "SHAKHTAYEVA", "KULYAIM",
    "Казахский паспорт (оригинальный тест)"
)

print(f"\n{'='*60}")
print("ИТОГИ ТЕСТОВ")
print(f"{'='*60}")
