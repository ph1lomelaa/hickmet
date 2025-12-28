"""
Тест MRZ паттерна с пробелами в фамилии
"""
import re

# Тестовый текст с MRZ строкой (как после OCR с пробелами)
test_text = """KAZAKHSTAN
P <KAZAKHME J ANOV<<KENES<<<<<<<<<<<<<<<<<<<<< <
N133579195KAZ71311185М3101115131118503741<<54"""

print("="*60)
print("ТЕСТОВЫЙ ТЕКСТ:")
print("="*60)
print(test_text)
print("\n")

EXCLUDE_WORDS = {
    'TYPI', 'TYPE', 'PASSPORT', 'CODE', 'STATE', 'GIVEN', 'NAMES',
    'GIVENNAMES', 'DATE', 'BIRTH', 'PLACE', 'ISSUE', 'EXPIRY',
    'AUTHORITY', 'MINISTRY', 'INTERNAL', 'AFFAIRS', 'KAZAKHSTAN',
    'КАЗАХСТАН', 'ПАСПОРТ', 'DATEOFBIRTH', 'PLACEOFBIRTH',
    'DATEOFISSUE', 'DATEOFEXPIRY', 'AUHORIY', 'CODEOFSTATE'
}

print("="*60)
print("ТЕСТИРУЕМ НОВЫЙ ПАТТЕРН:")
print("="*60)

# Новый паттерн с поддержкой пробелов
print("\nПаттерн: P\\s*<\\s*[A-Z]{3}\\s*<?\\s*([A-Z\\s<]+?)<<\\s*([A-Z]+)")
mrz_surname = re.search(r'P\s*<\s*[A-Z]{3}\s*<?\s*([A-Z\s<]+?)<<\s*([A-Z]+)', test_text)

if mrz_surname:
    surname_raw = mrz_surname.group(1)
    firstname = mrz_surname.group(2)

    print(f"\n✅ Найдено:")
    print(f"   Сырая фамилия: '{surname_raw}'")
    print(f"   Имя: '{firstname}'")

    # Очищаем фамилию: удаляем < и пробелы полностью (AKHME J ANOV -> AKHMEJANOV)
    surname = re.sub(r'[<\s]+', '', surname_raw).strip()

    print(f"\n🔄 После очистки:")
    print(f"   Фамилия: '{surname}'")
    print(f"   Имя: '{firstname}'")

    # Проверяем
    if surname and firstname and surname not in EXCLUDE_WORDS and firstname not in EXCLUDE_WORDS:
        print(f"\n✅ Проверка пройдена - не служебные слова")

        if surname == "AKHMEJANOV" and firstname == "KENES":
            print("\n🎉 УСПЕХ! Правильно распознано:")
            print(f"   Фамилия: {surname}")
            print(f"   Имя: {firstname}")
        else:
            print(f"\n⚠️ Получили: '{surname}' и '{firstname}'")
            print(f"   Ожидалось: 'AKHMEJANOV' и 'KENES'")
    else:
        print(f"\n❌ Отклонено - служебные слова или пустое значение")
else:
    print("\n❌ Паттерн не нашел совпадение")
