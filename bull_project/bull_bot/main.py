import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

# Импортируем настройки и хендлеры
from bull_project.bull_bot.config.constants import API_TOKEN
from bull_project.bull_bot.handlers import (
    booking_handlers, history_handlers, reschedule_handlers,
    care_handlers, admin_handlers, admin_applications, admin_reports
)
from bull_project.bull_bot.database.setup import init_db

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Путь к файлу блокировки
LOCK_FILE = "/tmp/bull_bot.lock"

def check_and_create_lock():
    """Проверяет наличие запущенного процесса и создает lock файл"""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                old_pid = int(f.read().strip())

            # Проверяем, жив ли процесс
            try:
                os.kill(old_pid, 0)  # Не убивает, просто проверяет
                logger.error(f"❌ Бот уже запущен (PID: {old_pid})")
                logger.error("   Остановите старый процесс перед запуском нового")
                return False
            except OSError:
                # Процесс не существует, удаляем старый lock
                logger.warning(f"⚠️ Найден устаревший lock файл (PID {old_pid}), удаляем")
                os.remove(LOCK_FILE)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка чтения lock файла: {e}, удаляем")
            try:
                os.remove(LOCK_FILE)
            except:
                pass

    # Создаем новый lock файл с текущим PID
    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"🔒 Lock файл создан (PID: {os.getpid()})")
        return True
    except Exception as e:
        logger.error(f"❌ Не удалось создать lock файл: {e}")
        return False

def remove_lock():
    """Удаляет lock файл при завершении"""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            logger.info("🔓 Lock файл удален")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка удаления lock файла: {e}")

async def main():
    logger.info("🚀 Запуск Bull Project Bot...")

    # 0. Проверка на множественный запуск
    if not check_and_create_lock():
        logger.error("❌ Завершение из-за конфликта процессов")
        return

    # 1. Инициализация базы данных
    try:
        await init_db()
        logger.info("✅ База данных подключена и проверена")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при подключении к БД: {e}")
        remove_lock()
        return

    # 2. Инициализация бота с поддержкой HTML (важно для ваших хендлеров)
    bot = Bot(
        token=API_TOKEN, 
        default=DefaultBotProperties(parse_mode="HTML")
    )
    dp = Dispatcher()

    # 3. Регистрация роутеров
    dp.include_router(booking_handlers.router)
    dp.include_router(history_handlers.router)
    dp.include_router(reschedule_handlers.router)
    dp.include_router(care_handlers.router)
    dp.include_router(admin_handlers.router)
    dp.include_router(admin_applications.router)
    dp.include_router(admin_reports.router)

    # 4. Очистка очереди обновлений и запуск
    # drop_pending_updates=True удаляет сообщения, присланные пока бот был выключен
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        logger.info("📡 Начинаем опрос Telegram (Polling)...")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        remove_lock()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Бот остановлен")
    finally:
        remove_lock()