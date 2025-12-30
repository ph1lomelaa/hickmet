from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from contextlib import suppress

from bull_project.bull_bot.core.google_sheets.client import get_accessible_tables
from bull_project.bull_bot.database.requests import (
    get_manager_packages,
    get_bookings_in_package,
    get_booking_by_id,
    mark_booking_cancelled,
    get_user_role,
    create_approval_request,
    update_booking_fields,
    get_admin_ids,
    get_admin_settings
)
from bull_project.bull_bot.core.google_sheets.writer import (
    clear_booking_in_sheets,
    write_cancelled_booking_red
)
from bull_project.bull_bot.config.keyboards import get_menu_by_role, kb_select_table
from bull_project.bull_bot.handlers.booking_handlers import BookingFlow
from bull_project.bull_bot.handlers.booking_handlers import _format_admin_booking
from bull_project.bull_bot.handlers.booking_handlers import send_webapp_link
from bull_project.bull_bot.config.constants import bot

router = Router()


@router.callback_query(F.data.startswith("reschedule:"))
async def start_reschedule(call: CallbackQuery, state: FSMContext):
    """Начало процесса переноса бронирования"""
    booking_id = int(call.data.split(":")[1])
    b = await get_booking_by_id(booking_id)

    if not b:
        await call.answer("Бронь не найдена")
        return

    # Формируем "виртуальный паспорт" из БД
    saved_passport_data = {
        'Last Name': b.guest_last_name,
        'First Name': b.guest_first_name,
        'Gender': b.gender,
        'Date of Birth': b.date_of_birth,
        'Document Number': b.passport_num,
        'Document Expiration': b.passport_expiry,
        'IIN': b.guest_iin,
        'client_phone': b.client_phone,
        'visa': b.visa_status,
        'avia_request': b.avia_request
    }

    # Записываем в память для переноса
    await state.update_data(
        is_reschedule=True,
        old_booking_id=booking_id,
        reschedule_passport=saved_passport_data,
        total_pilgrims=1,
        current_pilgrim=1,
        pilgrims_list=[saved_passport_data],
        contract=b.contract_number,
        region=b.region,
        room_type=b.room_type,
        meal_type=b.meal_type,
        price=b.price,
        amount_paid=b.amount_paid,
        exchange_rate=b.exchange_rate,
        discount=b.discount,
        source=b.source,
        comment=b.comment
    )

    # ДЕБАГ: Проверяем что данные сохранились
    data_check = await state.get_data()
    print(f"\n✅ ПЕРЕНОС ИНИЦИАЛИЗИРОВАН:")
    print(f"   Booking ID: {booking_id}")
    print(f"   Паломник: {b.guest_last_name} {b.guest_first_name}")
    print(f"   pilgrims_list установлен: {len(data_check.get('pilgrims_list', []))}")
    print(f"   reschedule_passport установлен: {bool(data_check.get('reschedule_passport'))}")
    print(f"   is_reschedule: {data_check.get('is_reschedule', False)}")

    # Выбор новой таблицы
    tables = get_accessible_tables()
    await call.message.answer(
        f"♻️ <b>Перенос паломника:</b> {b.guest_last_name} {b.guest_first_name}\n"
        f"📅 <b>Выберите НОВУЮ дату вылета:</b>",
        reply_markup=kb_select_table(tables),
        parse_mode="HTML"
    )

    await state.set_state(BookingFlow.choosing_table)
    await call.answer()


@router.callback_query(F.data == "history")
async def show_packages_list(call: CallbackQuery):
    """Показать список пакетов менеджера"""
    role = await get_user_role(call.from_user.id)
    packages = await get_manager_packages(call.from_user.id)

    if not packages:
        with suppress(TelegramBadRequest):
            await call.message.edit_text(
                "📂 <b>История пуста</b>\n\nУ вас пока нет завершенных бронирований.",
                reply_markup=get_menu_by_role(role),
                parse_mode="HTML"
            )
        return

    kb = []
    for pkg_name in packages:
        if not pkg_name:
            continue
        display_name = pkg_name[:35]
        cb_data = f"open_pkg:{pkg_name[:25]}"
        kb.append([InlineKeyboardButton(text=f"📦 {display_name}", callback_data=cb_data)])

    kb.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])

    with suppress(TelegramBadRequest):
        await call.message.edit_text(
            "📂 <b>ИСТОРИЯ ВАШИХ БРОНИРОВАНИЙ</b>\n\nВыберите пакет:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            parse_mode="HTML"
        )
    await call.answer()


@router.callback_query(F.data.startswith("open_pkg:"))
async def show_bookings_in_package(call: CallbackQuery):
    """Показать список бронирований в пакете"""
    pkg_short = call.data.split(":")[1]
    all_pkgs = await get_manager_packages(call.from_user.id)
    pkg_name = next((p for p in all_pkgs if p.startswith(pkg_short)), pkg_short)

    bookings = await get_bookings_in_package(call.from_user.id, pkg_name)

    if not bookings:
        await call.answer("В этом пакете нет активных броней", show_alert=True)
        return

    kb = []
    for b in bookings:
        btn_text = f"👤 {b.guest_last_name} {b.guest_first_name}"
        if b.sheet_row_number:
            btn_text += f" | Строка {b.sheet_row_number}"
        kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"view_booking:{b.id}")])

    kb.append([InlineKeyboardButton(text="🔙 К списку пакетов", callback_data="history")])

    await call.message.edit_text(
        f"📦 <b>Пакет:</b> {pkg_name}\n\n"
        f"Найдено бронирований: {len(bookings)}\n"
        f"Выберите паломника для просмотра:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("view_booking:"))
async def view_booking_card(call: CallbackQuery):
    """Показать подробную карточку бронирования"""
    booking_id = int(call.data.split(":")[1])
    b = await get_booking_by_id(booking_id)

    if not b:
        await call.answer("Бронь не найдена", show_alert=True)
        return

    # Формируем красивую карточку
    text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>📋 КАРТОЧКА БРОНИРОВАНИЯ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>👤 ФИО:</b> {b.guest_last_name} {b.guest_first_name}\n"
        f"<b>📅 Дата вылета:</b> {b.sheet_name}\n"
        f"<b>📦 Пакет:</b> {b.package_name}\n\n"
        f"<b>💰 Финансы:</b>\n"
        f"   • Сумма тура: ${b.price}\n"
        f"   • Оплачено: ${b.amount_paid or '0'}\n"
        f"   • Курс $: {b.exchange_rate or '-'}\n"
        f"   • Скидка: {b.discount or '-'}\n\n"
        f"<b>🏨 Размещение:</b>\n"
        f"   • Тип номера: {b.room_type}\n"
        f"   • Питание: {b.meal_type}\n\n"
        f"<b>📄 Документы:</b>\n"
        f"   • Паспорт: {b.passport_num}\n"
        f"   • Дата рождения: {b.date_of_birth}\n"
        f"   • Срок действия: {b.passport_expiry}\n"
        f"   • ИИН: {b.guest_iin or '-'}\n\n"
        f"<b>✈️ Виза/Авиа:</b>\n"
        f"   • Виза: {b.visa_status or '-'}\n"
        f"   • Авиа запрос: {b.avia or '-'}\n\n"
        f"<b>📍 Доп. информация:</b>\n"
        f"   • Регион: {b.region or '-'}\n"
        f"   • Город вылета: {b.departure_city or '-'}\n"
        f"   • Источник: {b.source or '-'}\n"
        f"   • Телефон: {b.client_phone or '-'}\n"
        f"   • Менеджер: {b.manager_name_text}\n"
    )

    if b.comment and b.comment != '-':
        text += f"   • Комментарий: {b.comment}\n"

    text += f"\n<b>📍 Строка в таблице:</b> {b.sheet_row_number or 'Не указано'}"

    back_cb = f"open_pkg:{b.package_name[:25]}"

    btns = [
        [InlineKeyboardButton(
            text="❌ ОТМЕНИТЬ БРОНЬ",
            callback_data=f"cancel_ask:{b.id}"
        )],
        [InlineKeyboardButton(
            text="✏️ ИЗМЕНИТЬ",
            callback_data=f"edit:{b.id}"
        )],
        [InlineKeyboardButton(
            text="♻️ ПЕРЕНЕСТИ БРОНЬ",
            callback_data=f"reschedule:{b.id}"
        )],
        [InlineKeyboardButton(text="🔙 Назад к пакету", callback_data=back_cb)],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ]

    await call.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=btns),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("cancel_ask:"))
async def ask_cancel(call: CallbackQuery):
    """Запрос отправляется админам на подтверждение"""
    bid = call.data.split(":")[1]
    b = await get_booking_by_id(int(bid))
    
    if not b:
        await call.answer("Бронь не найдена", show_alert=True)
        return

    # Создаём заявку и ставим статус pending_cancel
    # Сначала создаём запрос, чтобы избежать race condition
    req_id = await create_approval_request(b.id, "cancel", call.from_user.id)
    await update_booking_fields(b.id, {"status": "pending_cancel"})

    await call.message.edit_text(
        f"⏳ Запрос на отмену брони #{b.id} отправлен администраторам.\nОжидайте решения.",
        reply_markup=get_menu_by_role(await get_user_role(call.from_user.id)),
        parse_mode="HTML"
    )
    await notify_admins_cancel(b, req_id, call.from_user.id)
    await call.answer()


@router.callback_query(F.data.startswith("cancel_confirm:"))
async def process_cancel(call: CallbackQuery):
    """Обработка отмены бронирования"""
    await call.answer("Отмена через админа. Ожидайте решения.", show_alert=True)

# === ИЗМЕНЕНИЕ БРОНИ ===
@router.callback_query(F.data.startswith("edit:"))
async def start_edit(call: CallbackQuery, state: FSMContext):
    """Старт редактирования брони: отправляем данные в WebApp в режиме edit."""
    booking_id = int(call.data.split(":")[1])
    b = await get_booking_by_id(booking_id)

    if not b:
        await call.answer("Бронь не найдена", show_alert=True)
        return

    # Собираем данные паломника в формате, ожидаемом webapp
    pilgrim = {
        "Last Name": b.guest_last_name or "-",
        "First Name": b.guest_first_name or "-",
        "Gender": b.gender or "M",
        "Date of Birth": b.date_of_birth or "-",
        "Document Number": b.passport_num or "-",
        "Document Expiration": b.passport_expiry or "-",
        "IIN": b.guest_iin or "-",
        "client_phone": b.client_phone or "-",
        "passport_image_path": b.passport_image_path or None
    }

    # Сохраняем состояние для webapp
    await state.update_data(
        is_edit=True,
        edit_booking_id=booking_id,
        pilgrims_list=[pilgrim],
        current_sheet_id=b.table_id,
        current_sheet_name=b.sheet_name,
        selected_pkg_name=b.package_name,
        room=b.room_type or "-",
        meal=b.meal_type or "-",
        price=b.price or "0",
        amount_paid=b.amount_paid or "0",
        exchange_rate=b.exchange_rate or "-",
        discount=b.discount or "-",
        contract=b.contract_number or "-",
        region=b.region or "-",
        departure_city=b.departure_city or "-",
        source=b.source or "Edit",
        comment=b.comment or "-",
        train=b.train or "-",
        manager_name_text=b.manager_name_text or "-"
    )

    await call.message.answer(
        f"✏️ Редактирование брони #{booking_id}\nОткрываю форму...",
        parse_mode="HTML"
    )
    await send_webapp_link(call.message, state)
    await call.answer()

# ====== ВСПОМОГАТЕЛЬНОЕ: Уведомление админам о запросе отмены ======
async def notify_admins_cancel(booking, req_id: int, initiator_id: int):
    admin_ids = await get_admin_ids()
    if not admin_ids:
        return
    for admin_id in admin_ids:
        settings = await get_admin_settings(admin_id)
        if not settings or not settings.notify_cancel:
            continue
        text = _format_admin_booking(
            booking,
            "🛑 Запрос на отмену",
            extra=f"Инициатор: {initiator_id}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_cancel_ok:{req_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_cancel_reject:{req_id}")
            ]
        ])
        try:
            await bot.send_message(admin_id, text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            print(f"⚠️ Не удалось отправить уведомление админу {admin_id}: {e}")

# Отмена через текст "YES" отключена: теперь отмена только через админское подтверждение
