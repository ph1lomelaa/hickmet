import gspread
from google.oauth2.service_account import Credentials
import os

# Импортируем настройки из constants (обрати внимание на точку перед constants)
from .constants import SCOPES, CREDENTIALS_FILE, MOCK_MODE

# Глобальный клиент (чтобы не подключаться 100 раз)
_client = None

# Всегда используем тестовые таблицы
USE_TEST_SHEETS = True

def get_google_client():
    """
    Создает и возвращает авторизованный клиент Google Sheets.
    Если включен MOCK_MODE, возвращает None (имитация).
    """
    global _client

    # Если режим тестирования - не подключаемся к Google
    if MOCK_MODE:
        print("⚠️ [MOCK] Запрос клиента Google (возвращаем Fake Client)")
        return None

    if _client is not None:
        return _client

    print(f"🔄 Подключение к Google API...")

    # 1) Пытаемся взять ключи из переменной окружения (удобно для Koyeb/докера)
    env_creds = os.getenv("GOOGLE_CREDS_JSON")
    if env_creds:
        try:
            import json
            creds_dict = json.loads(env_creds)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            _client = gspread.authorize(creds)
            print("✅ Google Sheets клиент подключен из GOOGLE_CREDS_JSON")
            return _client
        except Exception as e:
            print(f"❌ Ошибка авторизации через GOOGLE_CREDS_JSON: {e}")

    # 2) Файл на диске (локальная разработка)
    print(f"🔑 Ищу файл ключей: {CREDENTIALS_FILE}")
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"❌ ОШИБКА: Файл ключей не найден!")
        print(f"👉 Положи файл service_account.json в папку bull_project/credentials/ или установи GOOGLE_CREDS_JSON")
        return None

    try:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        _client = gspread.authorize(creds)
        print("✅ Google Sheets клиент успешно подключен!")
        return _client
    except Exception as e:
        print(f"❌ Ошибка авторизации Google: {e}")
        return None
