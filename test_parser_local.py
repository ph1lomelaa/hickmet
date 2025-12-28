"""
Локальный тест парсера паспортов
"""
import sys
sys.path.insert(0, '/Users/muslimakosmagambetova/Downloads/tired2 2')

from bull_project.bull_bot.core.parsers.passport_parser import PassportParserEasyOCR

# Создаем тестовый текст как будто из EasyOCR
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

# Создаем парсер
parser = PassportParserEasyOCR(debug=True)

# Тестируем parse_text_fields напрямую
print("="*60)
print("ТЕСТИРУЕМ parse_text_fields:")
print("="*60)
result = parser.parse_text_fields(test_text)

print("\n")
print("="*60)
print("РЕЗУЛЬТАТ:")
print("="*60)
print(f"Фамилия: {result.last_name}")
print(f"Имя: {result.first_name}")
print(f"Дата рождения: {result.dob}")
print(f"Пол: {result.gender}")
print(f"Документ: {result.document_number}")
print(f"ИИН: {result.iin}")
print(f"Валидность: {result.is_valid}")
print("\n")

# Проверяем что получилось правильно
if result.last_name == "SHAKHTAYEVA" and result.first_name == "KULYAIM":
    print("✅ УСПЕХ! Имена извлечены правильно из MRZ строки")
else:
    print(f"❌ ОШИБКА! Получили '{result.last_name}' и '{result.first_name}'")
    print(f"   Ожидалось: 'SHAKHTAYEVA' и 'KULYAIM'")
