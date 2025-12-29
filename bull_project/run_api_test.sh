#!/bin/bash

# Скрипт для запуска ЛОКАЛЬНОГО API сервера с ТЕСТОВЫМИ таблицами
# Использование: ./run_api_test.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🌐 ════════════════════════════════════════════════"
echo "🌐 ЗАПУСК ЛОКАЛЬНОГО API СЕРВЕРА (ТЕСТОВЫЙ РЕЖИМ)"
echo "🌐 ════════════════════════════════════════════════"

# Загрузка переменных из .env.local
if [ -f ".env.local" ]; then
    echo "⚙️  Загрузка конфигурации из .env.local..."
    set -a
    source .env.local
    set +a
else
    echo "❌ Файл .env.local не найден!"
    exit 1
fi

# Нормализуем путь к БД в абсолютный (чтобы не было разных файлов при разных cwd)
DB_FILE="$(cd "$SCRIPT_DIR/bull_bot" && pwd)/bull_database.db"
export DATABASE_URL="sqlite+aiosqlite:///$DB_FILE"

# 🧪 ПРИНУДИТЕЛЬНО ВКЛЮЧАЕМ ТЕСТОВЫЙ РЕЖИМ
export USE_TEST_TABLE=true
export TEST_SPREADSHEET_ID=1trmbJ7MwizcUZc2So3_5nktx0NnciGaSv1foVpfwd54
export TEST_SPREADSHEET_NAME="JANUARY 2026 Копия"
export MOCK_MODE=false

# 🔧 DEBUG: Показать какой DATABASE_URL загружен
echo "🔍 DEBUG: DATABASE_URL = $DATABASE_URL"

# Настройки API сервера
export HOST=0.0.0.0
export PORT=8000

# Добавляем родительскую папку в PYTHONPATH
export PYTHONPATH="$(cd .. && pwd):$PYTHONPATH"

echo ""
echo "🧪 КОНФИГУРАЦИЯ API:"
echo "   ✅ USE_TEST_TABLE=true"
echo "   📋 Таблица: ${TEST_SPREADSHEET_NAME}"
echo "   🔗 ID: ${TEST_SPREADSHEET_ID:0:20}..."
echo "   🌐 URL: http://localhost:${PORT}"
echo ""
echo "⚠️  ВАЖНО:"
echo "   - API будет доступен по адресу: http://localhost:8000"
echo "   - Все запросы будут использовать ТЕСТОВУЮ таблицу"
echo "   - Production данные защищены"
echo ""
echo "💡 Для остановки нажмите Ctrl+C"
echo ""

# Обеспечиваем, что проект в PYTHONPATH
export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

# Активация виртуального окружения
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Запуск API сервера
echo "✅ Запускаю локальный API сервер..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 -m bull_bot.core.api_server
