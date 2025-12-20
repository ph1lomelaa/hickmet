import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

from bull_project.bull_bot.config.constants import API_TOKEN
from bull_project.bull_bot.handlers import booking_handlers, history_handlers, reschedule_handlers, care_handlers, \
    admin_handlers, admin_applications, admin_reports
from bull_project.bull_bot.database.setup import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("🚀 Запуск Bull Project Bot...")
    await init_db()

    logger.info("✅ База данных подключена и проверена")

    bot = Bot(token=API_TOKEN)
    dp = Dispatcher()

    dp.include_router(booking_handlers.router)
    dp.include_router(history_handlers.router)
    dp.include_router(reschedule_handlers.router)
    dp.include_router(care_handlers.router)
    dp.include_router(admin_handlers.router)
    dp.include_router(admin_applications.router)
    dp.include_router(admin_reports.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")