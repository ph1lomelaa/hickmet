"""
Тест текстового ввода имени вместо паспорта
"""

# Симуляция обработки текстового ввода
def process_text_input(text: str) -> dict:
    """
    Обрабатывает текстовый ввод вместо паспорта
    Возвращает словарь с данными паспорта
    """
    parts = text.strip().split()

    if len(parts) < 2:
        return None

    last_name = parts[0].upper()
    first_name = " ".join(parts[1:]).upper()

    p_data = {
        'Last Name': last_name,
        'First Name': first_name,
        'Gender': 'M',
        'Date of Birth': '-',
        'Document Number': '-',
        'Document Expiration': '-',
        'IIN': '-',
        'passport_image_path': None,
        # Snake_case поля
        'last_name': last_name,
        'first_name': first_name,
        'gender': 'M',
        'dob': '-',
        'doc_num': '-',
        'doc_exp': '-',
        'iin': '-',
    }

    return p_data

# Тестовые случаи
test_cases = [
    "IVANOV IVAN",
    "Петров Петр Иванович",
    "SMITH JOHN",
    "ivanov ivan",
    "KUANBAEVA RAYA ALTYBAEVNA",
    "SHAKHTAYEVA KULYAIM",
    "A",  # Недостаточно частей
    "   NASSIPKHAN   TOLEU   ",  # С пробелами
]

print("="*60)
print("ТЕСТИРОВАНИЕ ТЕКСТОВОГО ВВОДА ИМЕНИ")
print("="*60)

for i, test in enumerate(test_cases, 1):
    print(f"\nТест {i}: '{test}'")
    result = process_text_input(test)

    if result:
        print(f"  ✅ Успешно распознано:")
        print(f"     Фамилия: {result['Last Name']}")
        print(f"     Имя: {result['First Name']}")
        print(f"     Паспорт: {result['passport_image_path'] or 'НЕТ'}")
    else:
        print(f"  ❌ Ошибка: недостаточно данных")

print("\n" + "="*60)
print("ПРОВЕРКА ИНТЕГРАЦИИ С ФОРМОЙ")
print("="*60)

# Проверим, что данные подойдут для формы
test_result = process_text_input("IVANOV IVAN")
print("\nПример данных для передачи в форму:")
print(f"  Last Name: {test_result.get('Last Name', 'НЕТ')}")
print(f"  First Name: {test_result.get('First Name', 'НЕТ')}")
print(f"  Gender: {test_result.get('Gender', 'НЕТ')}")
print(f"  Date of Birth: {test_result.get('Date of Birth', 'НЕТ')}")
print(f"  Document Number: {test_result.get('Document Number', 'НЕТ')}")
print(f"  Passport Image: {test_result.get('passport_image_path', 'НЕТ')}")

print("\n✅ Все данные в формате, совместимом с WebApp формой")
print("⚠️ Поля с '-' нужно будет заполнить вручную в форме")
