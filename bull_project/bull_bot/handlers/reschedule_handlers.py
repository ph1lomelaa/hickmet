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
    get_booking_by_id, add_booking_to_db, update_booking_row, mark_booking_rescheduled,
    get_user_by_id, create_approval_request, update_booking_fields,
    get_admin_ids, get_admin_settings
)
from bull_project.bull_bot.core.google_sheets.writer import (
    save_group_booking, check_train_exists, clear_booking_in_sheets, write_rescheduled_booking_red
)
# Импортируем BookingFlow из booking_handlers, чтобы состояния не конфликтовали
from bull_project.bull_bot.handlers.booking_handlers import BookingFlow, _format_admin_booking
from bull_project.bull_bot.config.constants import bot

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

        # Готовим данные для новой брони (без записи в Sheets, статус pending_reschedule)
        new_booking_data = {
            'table_id': data['current_sheet_id'],
            'sheet_name': data['current_sheet_name'],
            'package_name': data['selected_pkg_name'],
            'room_type': data.get('room', 'Standard'),
            'meal_type': data.get('meal', 'BB'),
            'price': data.get('price', '0'),
            'amount_paid': data.get('amount_paid', '0'),
            'exchange_rate': data.get('exchange_rate', '-'),
            'discount': data.get('discount', '-'),
            'contract_number': data.get('contract', '-'),
            'region': data.get('region', '-'),
            'departure_city': data.get('departure_city', '-'),
            'source': data.get('source', 'Reschedule'),
            'comment': f"ПЕРЕНОС: {data.get('comment', '-')}",
            'train': data.get('train', '-'),
            'manager_name_text': manager_real_name,
            'visa_status': passport_data.get('visa', '-'),
            'avia': passport_data.get('avia_request', '-'),
            'client_phone': passport_data.get('client_phone', '-'),
            'guest_last_name': passport_data.get('Last Name', ''),
            'guest_first_name': passport_data.get('First Name', ''),
            'gender': passport_data.get('Gender', ''),
            'date_of_birth': passport_data.get('Date of Birth', ''),
            'passport_num': passport_data.get('Document Number', ''),
            'passport_expiry': passport_data.get('Document Expiration', ''),
            'guest_iin': passport_data.get('IIN', ''),
            'placement_type': data.get('placement_type', 'separate'),
            'passport_image_path': passport_data.get('passport_image_path', None),
            'status': 'pending_reschedule'
        }

        new_booking_id = await add_booking_to_db(new_booking_data, message.chat.id)

        # Создаем заявку для админов, храним old_id в comment
        # Сначала создаём запрос, чтобы избежать race condition
        old_id = data.get('old_booking_id')
        comment = f"old:{old_id}" if old_id else None
        req_id = await create_approval_request(new_booking_id, "reschedule", message.chat.id, comment=comment)

        # Старую бронь ставим в pending_reschedule
        if old_id:
            await update_booking_fields(old_id, {"status": "pending_reschedule"})

        await message.answer(
            f"♻️ Запрос на перенос брони #{old_id} → #{new_booking_id} отправлен админам.\nОжидайте подтверждения.",
            reply_markup=get_menu_by_role(user_db.role if user_db else 'manager'),
            parse_mode="HTML"
        )
        await notify_admins_reschedule(new_booking_id, old_id, req_id, message.chat.id)

    except Exception as e:
        await message.answer(f"❌ Ошибка переноса: {e}")

    await state.clear()


async def notify_admins_reschedule(new_booking_id: int, old_id: int, req_id: int, initiator_id: int):
    admin_ids = await get_admin_ids()
    if not admin_ids:
        return
    booking = await get_booking_by_id(new_booking_id)
    if not booking:
        return
    for admin_id in admin_ids:
        settings = await get_admin_settings(admin_id)
        if not settings or not settings.notify_reschedule:
            continue
        text = _format_admin_booking(
            booking,
            "♻️ Запрос на перенос",
            extra=f"Старый #{old_id} → Новый #{booking.id}\nИнициатор: {initiator_id}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить перенос", callback_data=f"admin_resched_ok:{req_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_resched_reject:{req_id}")
            ]
        ])
        try:
            await bot.send_message(admin_id, text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            print(f"⚠️ Не удалось отправить уведомление админу {admin_id}: {e}")
