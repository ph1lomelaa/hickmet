import os
import logging
from datetime import datetime
from sqlalchemy import select
from bull_project.bull_bot.database.setup import async_session
from bull_project.bull_bot.database.models import Booking

logger = logging.getLogger(__name__)

async def clean_old_passports():
    """
    Проверяет все брони. Если дата вылета (sheet_name) прошла,
    удаляет файл паспорта с диска и очищает запись в БД.
    """
    print("🧹 Запуск очистки старых паспортов...")
    deleted_count = 0
    errors = 0

    async with async_session() as session:
        # Получаем все брони, у которых есть сохраненный путь к паспорту
        query = select(Booking).where(Booking.passport_image_path.isnot(None))
        bookings = await session.scalars(query)

        today = datetime.now().date()
        current_year = datetime.now().year

        for b in bookings:
            try:
                # 1. Парсим дату вылета из названия листа (например "13.01")
                # Предполагаем формат "ДД.ММ"
                date_str = b.sheet_name.split()[0] # Берем первое слово (если там "13.01 HIKMA")
                # Чистим от лишнего
                date_str = "".join([c for c in date_str if c.isdigit() or c == "."])

                if len(date_str) < 5: continue # Непонятная дата

                flight_date = datetime.strptime(f"{date_str}.{current_year}", "%d.%m.%Y").date()

                # Если это декабрь, а сейчас январь - значит полет был в прошлом году
                if flight_date.month == 12 and today.month == 1:
                    flight_date = flight_date.replace(year=current_year - 1)

                # 2. Если дата вылета прошла (вчера или раньше)
                if flight_date < today:
                    file_path = b.passport_image_path

                    # Удаляем физически
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"🗑 Удален файл: {file_path}")

                    # Очищаем поле в БД
                    b.passport_image_path = None
                    deleted_count += 1

            except Exception as e:
                # logger.error(f"Ошибка при очистке брони {b.id}: {e}")
                errors += 1
                continue

        await session.commit()

    return f"Очищено {deleted_count} файлов паспортов."