#!/bin/bash

# Скрипт для запуска ТЕСТОВОГО бота локально
# Использование: ./run_test.sh

# Переходим в директорию скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Используем Python 3.11 (совместим с pydantic)
PYTHON_CMD="python3.11"

echo "🧪 ════════════════════════════════════════════════"
echo "🧪 ЗАПУСК ТЕСТОВОГО БОТА"
echo "🧪 ════════════════════════════════════════════════"
echo "📁 Рабочая директория: $SCRIPT_DIR"

# Проверка наличия .env.local (тестовый конфиг)
if [ ! -f ".env.local" ]; then
    echo ""
    echo "❌ Файл .env.local не найден!"
    echo ""
    echo "📝 Создайте .env.local на основе .env.test:"
    echo "   cp .env.test .env.local"
    echo ""
    echo "📝 Затем отредактируйте .env.local:"
    echo "   1. Создайте ТЕСТОВОГО бота через @BotFather"
    echo "   2. Вставьте токен в API_TOKEN"
    echo "   3. Измените пароли (ADMIN_PASSWORD, MANAGER_PASSWORD, CARE_PASSWORD)"
    echo "   4. Укажите путь к credentials для ТЕСТОВОЙ Google таблицы"
    echo ""
    echo "💡 Для продакшн бота используйте ./run_local.sh"
    exit 1
fi

# Проверка виртуального окружения
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Виртуальное окружение не найдено. Создаю..."
    $PYTHON_CMD -m venv venv
    echo "✅ Виртуальное окружение создано"
fi

# Активация виртуального окружения
echo "🔄 Активация виртуального окружения..."
source venv/bin/activate

# Установка зависимостей
echo "📥 Проверка зависимостей..."
pip install -q -r requirements.txt

# Загрузка переменных окружения из .env.local (ТЕСТОВЫЙ КОНФИГ)
echo "⚙️  Загрузка ТЕСТОВОЙ конфигурации из .env.local..."
set -a
source .env.local
set +a

# Нормализуем путь к БД (SQLite) в абсолютный, чтобы не цеплялся postgres из окружения
DB_FILE="$(cd "$SCRIPT_DIR/bull_bot" && pwd)/bull_database.db"
export DATABASE_URL="sqlite+aiosqlite:///$DB_FILE"

# 🧪 ПРИНУДИТЕЛЬНО ВКЛЮЧАЕМ ТЕСТОВЫЙ РЕЖИМ
export USE_TEST_TABLE=true
export TEST_SPREADSHEET_ID=1trmbJ7MwizcUZc2So3_5nktx0NnciGaSv1foVpfwd54
export TEST_SPREADSHEET_NAME="JANUARY 2026 Копия"
export MOCK_MODE=false

# 🔧 DEBUG: Показать какой DATABASE_URL загружен
echo "🔍 DEBUG: DATABASE_URL = $DATABASE_URL"

# Добавляем родительскую папку в PYTHONPATH
export PYTHONPATH="$(cd .. && pwd):$PYTHONPATH"
echo "📍 PYTHONPATH: $PYTHONPATH"

# Проверка API_TOKEN
if [ -z "$API_TOKEN" ] || [ "$API_TOKEN" = "your_test_bot_token_here" ]; then
    echo ""
    echo "⚠️  ВНИМАНИЕ: API_TOKEN не установлен!"
    echo ""
    echo "📝 Шаги для создания тестового бота:"
    echo "   1. Откройте @BotFather в Telegram"
    echo "   2. Отправьте /newbot"
    echo "   3. Укажите имя: 'My Test Bull Bot'"
    echo "   4. Укажите username: 'my_test_bull_bot' (должен быть уникальным)"
    echo "   5. Скопируйте полученный токен"
    echo "   6. Вставьте в .env.local: API_TOKEN=полученный_токен"
    echo ""
    exit 1
fi

# Вывод конфигурации
echo ""
echo "🧪 ════════════════════════════════════════════════"
echo "🧪 ТЕСТОВАЯ КОНФИГУРАЦИЯ"
echo "🧪 ════════════════════════════════════════════════"
echo "🤖 API TOKEN: ${API_TOKEN:0:10}...${API_TOKEN: -5}"
echo "🗄️  DATABASE: ${DATABASE_URL:-./bull_bot/bull_database.db}"
echo "🔧 OCR ENGINE: ${PASSPORT_ENGINE:-easyocr}"
echo "🔑 ADMIN PASSWORD: ${ADMIN_PASSWORD:0:3}***"
echo "🔑 MANAGER PASSWORD: ${MANAGER_PASSWORD:0:3}***"
echo "🔑 CARE PASSWORD: ${CARE_PASSWORD:0:3}***"
echo ""
echo "📊 GOOGLE SHEETS: 🧪 ТЕСТОВЫЙ РЕЖИМ"
echo "   ✅ USE_TEST_TABLE=true"
echo "   📋 Таблица: ${TEST_SPREADSHEET_NAME}"
echo "   🔗 ID: ${TEST_SPREADSHEET_ID:0:20}..."
echo "🧪 ════════════════════════════════════════════════"
echo ""

# Предупреждение
echo "⚠️  ВАЖНО:"
echo "   - Это ТЕСТОВЫЙ бот, не используйте в продакшене"
echo "   - Используется отдельная база данных"
echo "   - Убедитесь, что Google Sheets тоже тестовая"
echo ""
echo "💡 Для остановки нажмите Ctrl+C"
echo ""

# Пауза 2 секунды
sleep 2

# Запуск бота
echo "✅ Запускаю ТЕСТОВОГО бота..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
$PYTHON_CMD -m bull_bot.main
