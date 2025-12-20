from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

# Импорты
from bull_project.bull_bot.config.keyboards import (
    kb_select_table, kb_select_sheet, kb_select_package,
    room_kb, meal_kb, get_menu_by_role
)
from bull_project.bull_bot.core.google_sheets.client import (
    get_accessible_tables, get_packages_from_sheet, get_sheet_names
)
from bull_project.bull_bot.database.requests import (
    get_booking_by_id, add_booking_to_db, update_booking_row, mark_booking_cancelled, get_user_by_id
)
from bull_project.bull_bot.core.google_sheets.writer import (
    save_group_booking, check_train_exists, clear_booking_in_sheets
)
# Импортируем BookingFlow из booking_handlers, чтобы состояния не конфликтовали
from bull_project.bull_bot.handlers.booking_handlers import BookingFlow

router = Router()

# === FSM для Переноса ===
class RescheduleFlow(StatesGroup):
    choosing_table = State()
    choosing_date = State()
    choosing_pkg = State()

    # Новые вопросы (если перенос идет вручную, а не через Web App)
    waiting_meal = State()
    waiting_room = State()
    waiting_price = State()
    waiting_train = State()
    waiting_comment = State()

    choosing_placement = State()
    waiting_placement_name = State()

# ... (Логику выбора таблицы и пакета start_reschedule оставляем в history_handlers) ...

# === ФИНАЛИЗАЦИЯ ПЕРЕНОСА ===
# Эту функцию нужно обновить, чтобы она писала в БД новые поля

async def finalize_reschedule(message: Message, state: FSMContext):
    try:
        data = await state.get_data()

        # Получаем данные старой брони (паспорт и т.д.)
        passport_data = data.get('reschedule_passport')

        # Данные менеджера
        user_db = await get_user_by_id(message.chat.id)
        manager_real_name = user_db.full_name if user_db else "Manager"

        # Общие данные для БД и Гугла
        common_data = {
            'table_id': data['current_sheet_id'],
            'sheet_name': data['current_sheet_name'],
            'package_name': data['selected_pkg_name'],
            'room_type': data.get('room', 'Standard'),
            'meal': data.get('meal', 'BB'),
            'price': data.get('price', '0'),
            'amount_paid': data.get('amount_paid', '0'),
            'exchange_rate': data.get('exchange_rate', '-'),
            'discount': data.get('discount', '-'),
            'contract': data.get('contract', '-'), # 🔥 НОВОЕ ПОЛЕ

            'region': data.get('region', '-'),
            'departure_city': data.get('departure_city', '-'),
            'source': data.get('source', 'Reschedule'),

            'comment': f"ПЕРЕНОС: {data.get('comment', '-')}",
            'manager': manager_real_name,
            'train': data.get('train', '-'),
            'created_by_name': manager_real_name
        }

        # Объединяем с паспортом
        full_data_for_db = {
            **common_data,
            'passport_data': passport_data,
            # Если есть сохраненные данные визы/авиа из старой брони
            'visa': passport_data.get('visa', '-'),
            'avia_request': passport_data.get('avia_request', '-'),
            'client_phone': passport_data.get('client_phone', '-'),
            'manager_name_text': manager_real_name
        }

        # 1. Запись в БД
        new_booking_id = await add_booking_to_db(full_data_for_db, message.chat.id)

        # 2. Запись в Гугл (Только 1 человек при переносе)
        # placement_mode='separate' потому что переносим по одному
        saved_rows = await save_group_booking(
            [passport_data],
            common_data,
            placement_mode='separate',
            specific_row=data.get('specific_row'),
            is_share=data.get('is_share', False)
        )

        if saved_rows:
            # Обновляем строку в БД
            await update_booking_row(new_booking_id, saved_rows[0])

            # 🔥 УДАЛЕНИЕ СТАРОЙ БРОНИ
            old_id = data.get('old_booking_id')
            old_b = await get_booking_by_id(old_id)

            if old_b and old_b.sheet_row_number:
                await clear_booking_in_sheets(old_b.table_id, old_b.sheet_name, old_b.sheet_row_number, old_b.package_name)
                await mark_booking_cancelled(old_id)

            await message.answer(
                f"✅ <b>Успешно перенесено!</b>\n"
                f"Старая бронь #{old_id} удалена.\n"
                f"Новая бронь #{new_booking_id} создана на строке {saved_rows[0]}.",
                reply_markup=get_menu_by_role(user_db.role if user_db else 'manager'),
                parse_mode="HTML"
            )
        else:
            await message.answer("⚠️ Ошибка записи в таблицу! (Бронь в БД создана, но в Гугл не попала).")

    except Exception as e:
        await message.answer(f"❌ Ошибка переноса: {e}")

    await state.clear()