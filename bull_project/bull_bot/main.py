import asyncio
import logging
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

async def main():
    logger.info("🚀 Запуск Bull Project Bot...")
    
    # 1. Инициализация базы данных
    try:
        await init_db()
        logger.info("✅ База данных подключена и проверена")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при подключении к БД: {e}")
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

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Бот остановлен")