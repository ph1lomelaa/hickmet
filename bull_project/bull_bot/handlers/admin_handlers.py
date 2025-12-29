from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder # 🔥
from contextlib import suppress
from aiogram.exceptions import TelegramBadRequest

from bull_project.bull_bot.core.google_sheets.four_u_logic import find_availability_for_4u, create_4u_sheet
from bull_project.bull_bot.database.models import Base
from bull_project.bull_bot.database.requests import (
    get_active_4u_requests, get_4u_request_by_id, update_4u_status,
    get_approval_request, update_approval_status, get_booking_by_id,
    mark_booking_cancelled, update_booking_fields, get_user_role, get_manager_packages, get_bookings_in_package,
    get_admin_settings, set_admin_settings, update_booking_row
)
from bull_project.bull_bot.config.keyboards import admin_kb
from bull_project.bull_bot.config.constants import bot
from bull_project.bull_bot.database.setup import engine
from bull_project.bull_bot.core.google_sheets.writer import (
    clear_booking_in_sheets, write_cancelled_booking_red,
    save_group_booking, write_rescheduled_booking_red
)
from bull_project.bull_bot.database.requests import mark_booking_rescheduled

router = Router()

# TODO: Разместите файлы на GitHub Pages или другом хостинге
ADMIN_PANEL_URL = "https://ph1lomelaa.github.io/book/admin-panel.html"
ADMIN_BOOKINGS_URL = "https://ph1lomelaa.github.io/book/admin-bookings.html"
ADMIN_CREATE_URL = "https://ph1lomelaa.github.io/book/admin-create-booking.html"
ADMIN_REQUESTS_URL = "https://ph1lomelaa.github.io/book/admin-requests.html"

# === 1. СПИСОК ЗАЯВОК ===
@router.callback_query(F.data == "admin_stats")
async def show_4u_list(call: CallbackQuery):
    requests = await get_active_4u_requests()

    if not requests:
        with suppress(TelegramBadRequest):
            await call.message.edit_text("📭 <b>Активных заявок 4U нет.</b>", reply_markup=admin_kb(), parse_mode="HTML")
        return

    builder = InlineKeyboardBuilder()
    for req in requests:
        icon = "🔴" if req.status == 'pending' else "🟢"
        builder.button(text=f"{icon} #{req.id} | {req.manager_name} | {req.dates}", callback_data=f"view_4u:{req.id}")

    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu"))

    with suppress(TelegramBadRequest):
        await call.message.edit_text("📋 <b>ЗАЯВКИ НА 4U:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()

# === 2. ПРОСМОТР ЗАЯВКИ ===
@router.callback_query(F.data.startswith("view_4u:"))
async def view_request(call: CallbackQuery):
    req_id = int(call.data.split(":")[1])
    req = await get_4u_request_by_id(req_id)

    if not req:
        await call.answer("Заявка не найдена")
        return

    text = (
        f"📝 <b>ЗАЯВКА #{req.id}</b>\n"
        f"👤 <b>Менеджер:</b> {req.manager_name}\n"
        f"📅 <b>Даты:</b> {req.dates}\n"
        f"👥 <b>Людей:</b> {req.pilgrim_count}\n"
        f"🛏 <b>Номер:</b> {req.room_type}\n"
        f"📊 <b>Статус:</b> {req.status}\n"
    )

    kb = InlineKeyboardBuilder()
    if req.status == 'pending':
        # Кнопки в 2 колонки
        kb.button(text="🔍 Проверить места", callback_data=f"check_4u:{req.id}")
        kb.button(text="🚀 Создать лист", callback_data=f"approve_start:{req.id}")
        kb.button(text="❌ Отклонить", callback_data=f"reject_4u:{req.id}")
        kb.adjust(2) # Красиво упаковываем

    kb.row(InlineKeyboardButton(text="🔙 К списку", callback_data="admin_stats"))

    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# === 3. ПРОВЕРКА МЕСТ ===
@router.callback_query(F.data.startswith("check_4u:"))
async def check_availability(call: CallbackQuery):
    req_id = int(call.data.split(":")[1])
    req = await get_4u_request_by_id(req_id)

    await call.message.edit_text("⏳ <b>Сканирую таблицу...</b>", parse_mode="HTML")

    results = await find_availability_for_4u(req.table_id, req.dates, req.pilgrim_count, req.room_type)

    kb = InlineKeyboardBuilder()
    if not results:
        text = "🤷‍♂️ <b>Свободных блоков не найдено.</b>\nСоздавайте новый лист."
        kb.button(text="➕ Создать новый лист", callback_data=f"approve_start:{req_id}")
    else:
        text = "🔎 <b>Найдены места:</b>\n\n"
        for r in results:
            text += f"🔹 {r['package']}\n📄 {r['sheet']}\n🧹 Удалить: {r['rows_to_clear']}\n---\n"

        kb.button(text="🚀 Создать лист", callback_data=f"approve_start:{req_id}")

    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data=f"view_4u:{req_id}"))

    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# === 4. СОЗДАНИЕ ===
@router.callback_query(F.data.startswith("approve_start:"))
async def create_sheet_confirm(call: CallbackQuery):
    req_id = int(call.data.split(":")[1])
    req = await get_4u_request_by_id(req_id)

    text = f"🚀 <b>Создание листа 4U</b>\n📅 {req.dates}\n🛏 {req.pilgrim_count} мест ({req.room_type})\n\nПодтверждаете?"

    kb = InlineKeyboardBuilder()
    kb.button(text="🔥 ПОДТВЕРДИТЬ", callback_data=f"do_create_4u:{req_id}")
    kb.button(text="Отмена", callback_data=f"view_4u:{req_id}")
    kb.adjust(2)

    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("do_create_4u:"))
async def execute_creation(call: CallbackQuery):
    req_id = int(call.data.split(":")[1])
    req = await get_4u_request_by_id(req_id)

    await call.message.edit_text("⏳ <b>Создаю лист и объединяю ячейки...</b>", parse_mode="HTML")

    success, result_msg = await create_4u_sheet(
        req.table_id, req.dates, req.pilgrim_count, req.room_type, req.manager_name
    )

    if success:
        await update_4u_status(req_id, "approved", sheet_name=result_msg)
        try: await bot.send_message(req.manager_id, f"✅ <b>Заявка 4U одобрена!</b>\nЛист: <code>{result_msg}</code>")
        except: pass

        await call.message.edit_text(
            f"✅ <b>Готово!</b> Лист <code>{result_msg}</code> создан.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К списку", callback_data="admin_stats")]])
        )
    else:
        await call.message.edit_text(f"❌ Ошибка: {result_msg}",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data=f"view_4u:{req_id}")]]))

# === 5. ОТКЛОНЕНИЕ ===
@router.callback_query(F.data.startswith("reject_4u:"))
async def reject_request(call: CallbackQuery):
    req_id = int(call.data.split(":")[1])
    req = await get_4u_request_by_id(req_id)

    if req:
        await update_4u_status(req_id, "rejected")
        try: await bot.send_message(req.manager_id, f"❌ Заявка 4U на {req.dates} отклонена.")
        except: pass

    await call.message.edit_text(
        "❌ Заявка отклонена.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К списку", callback_data="admin_stats")]])
    )

# === ОДОБРЕНИЕ ОТМЕНЫ/ПЕРЕНОСА ===
async def _perform_cancel(booking):
    sheets_cleared = False
    if booking.sheet_row_number and booking.table_id and booking.sheet_name:
        sheets_cleared = await clear_booking_in_sheets(
            booking.table_id,
            booking.sheet_name,
            booking.sheet_row_number,
            booking.package_name
        )

    red_written = False
    if booking.table_id and booking.sheet_name and booking.package_name:
        guest_name = f"{booking.guest_last_name} {booking.guest_first_name}"
        red_written = await write_cancelled_booking_red(
            booking.table_id,
            booking.sheet_name,
            booking.package_name,
            guest_name
        )
    await mark_booking_cancelled(booking.id)
    return sheets_cleared, red_written

@router.callback_query(F.data.startswith("admin_cancel_ok:"))
async def admin_cancel_ok(call: CallbackQuery):
    # Проверка прав доступа
    role = await get_user_role(call.from_user.id)
    if role != "admin":
        await call.answer("❌ Только администраторы могут подтверждать отмену", show_alert=True)
        return

    req_id = int(call.data.split(":")[1])
    req = await get_approval_request(req_id)
    if not req or req.status != "pending":
        await call.answer("Заявка не найдена или уже обработана", show_alert=True)
        return
    booking = await get_booking_by_id(req.booking_id)
    if not booking:
        await call.answer("Бронь не найдена", show_alert=True)
        return

    await call.message.edit_text("⏳ Обрабатываю отмену...", parse_mode="HTML")
    sheets_cleared, red_written = await _perform_cancel(booking)
    await update_approval_status(req_id, "approved")

    status_parts = []
    status_parts.append("✅ Данные очищены из таблицы" if sheets_cleared else "⚠️ Не удалось очистить данные")
    status_parts.append("✅ Отмена записана красным" if red_written else "⚠️ Не удалось записать отмену красным")

    text = (
        f"🗑 <b>Бронь #{booking.id} отменена</b>\n"
        f"Пакет: {booking.package_name}\n"
        f"Паломник: {booking.guest_last_name} {booking.guest_first_name}\n\n"
        + "\n".join(status_parts)
    )
    await call.message.edit_text(text, reply_markup=admin_kb(), parse_mode="HTML")
    # Уведомляем инициатора
    try:
        await bot.send_message(req.initiator_id, f"✅ Отмена брони #{booking.id} одобрена админом.")
    except: pass

@router.callback_query(F.data.startswith("admin_cancel_reject:"))
async def admin_cancel_reject(call: CallbackQuery):
    # Проверка прав доступа
    role = await get_user_role(call.from_user.id)
    if role != "admin":
        await call.answer("❌ Только администраторы могут отклонять отмену", show_alert=True)
        return

    req_id = int(call.data.split(":")[1])
    req = await get_approval_request(req_id)
    if not req or req.status != "pending":
        await call.answer("Заявка не найдена или уже обработана", show_alert=True)
        return
    booking = await get_booking_by_id(req.booking_id)
    if booking:
        await update_booking_fields(booking.id, {"status": "new"})
    await update_approval_status(req_id, "rejected")

    await call.message.edit_text("❌ Заявка на отмену отклонена.", reply_markup=admin_kb(), parse_mode="HTML")
    try:
        await bot.send_message(req.initiator_id, f"❌ Отмена брони #{req.booking_id} отклонена админом.")
    except: pass


@router.callback_query(F.data.startswith("admin_resched_ok:"))
async def admin_resched_ok(call: CallbackQuery):
    # Проверка прав доступа
    role = await get_user_role(call.from_user.id)
    if role != "admin":
        await call.answer("❌ Только администраторы могут подтверждать перенос", show_alert=True)
        return

    req_id = int(call.data.split(":")[1])
    req = await get_approval_request(req_id)
    if not req or req.status != "pending":
        await call.answer("Заявка не найдена или уже обработана", show_alert=True)
        return
    new_booking = await get_booking_by_id(req.booking_id)
    if not new_booking:
        await call.answer("Новая бронь не найдена", show_alert=True)
        return
    old_id = None
    if req.comment and req.comment.startswith("old:"):
        try:
            old_id = int(req.comment.split("old:")[1])
        except:
            old_id = None
    old_booking = await get_booking_by_id(old_id) if old_id else None

    await call.message.edit_text("⏳ Обрабатываю перенос...", parse_mode="HTML")

    # Запись новой брони в Sheets
    common_data = {
        'table_id': new_booking.table_id,
        'sheet_name': new_booking.sheet_name,
        'package_name': new_booking.package_name,
        'room_type': new_booking.room_type,
        'meal_type': new_booking.meal_type,
        'price': new_booking.price,
        'amount_paid': new_booking.amount_paid,
        'exchange_rate': new_booking.exchange_rate,
        'discount': new_booking.discount,
        'contract_number': new_booking.contract_number,
        'region': new_booking.region,
        'departure_city': new_booking.departure_city,
        'source': new_booking.source,
        'comment': new_booking.comment,
        'manager_name_text': new_booking.manager_name_text,
        'train': new_booking.train,
    }
    person = {
        "Last Name": new_booking.guest_last_name,
        "First Name": new_booking.guest_first_name,
        "Gender": new_booking.gender,
        "Date of Birth": new_booking.date_of_birth,
        "Document Number": new_booking.passport_num,
        "Document Expiration": new_booking.passport_expiry,
        "IIN": new_booking.guest_iin,
        "client_phone": new_booking.client_phone,
        "passport_image_path": new_booking.passport_image_path
    }
    saved_rows = await save_group_booking([person], common_data, new_booking.placement_type or 'separate')
    if saved_rows:
        await update_booking_row(new_booking.id, saved_rows[0])
        await update_booking_fields(new_booking.id, {"status": "new"})
    else:
        # Rollback: откатываем статус старой брони и отклоняем запрос
        if old_booking:
            await update_booking_fields(old_booking.id, {"status": "new"})
        await update_approval_status(req_id, "rejected")
        await call.message.edit_text("❌ Не удалось записать новую бронь в таблицу", reply_markup=admin_kb(), parse_mode="HTML")
        return

    # Обработка старой брони
    if old_booking:
        if old_booking.sheet_row_number and old_booking.table_id and old_booking.sheet_name:
            try:
                await clear_booking_in_sheets(old_booking.table_id, old_booking.sheet_name, old_booking.sheet_row_number, old_booking.package_name)
            except: pass
        try:
            guest_name = f"{old_booking.guest_last_name} {old_booking.guest_first_name}"
            await write_rescheduled_booking_red(old_booking.table_id, old_booking.sheet_name, old_booking.package_name, guest_name)
        except: pass
        await mark_booking_rescheduled(old_booking.id, comment=f"Перенесено в #{new_booking.id}")

    await update_approval_status(req_id, "approved")

    text = (
        f"♻️ <b>Перенос одобрен</b>\n"
        f"Старый #{old_id or '-'} → Новый #{new_booking.id}\n"
        f"Пакет: {new_booking.package_name}\n"
        f"Строка: {saved_rows[0]}"
    )
    await call.message.edit_text(text, reply_markup=admin_kb(), parse_mode="HTML")
    try:
        await bot.send_message(req.initiator_id, f"✅ Перенос брони #{old_id} → #{new_booking.id} одобрен админом.")
    except: pass


@router.callback_query(F.data.startswith("admin_resched_reject:"))
async def admin_resched_reject(call: CallbackQuery):
    # Проверка прав доступа
    role = await get_user_role(call.from_user.id)
    if role != "admin":
        await call.answer("❌ Только администраторы могут отклонять перенос", show_alert=True)
        return

    req_id = int(call.data.split(":")[1])
    req = await get_approval_request(req_id)
    if not req or req.status != "pending":
        await call.answer("Заявка не найдена или уже обработана", show_alert=True)
        return
    new_booking = await get_booking_by_id(req.booking_id)
    old_id = None
    if req.comment and req.comment.startswith("old:"):
        try:
            old_id = int(req.comment.split("old:")[1])
        except:
            old_id = None
    if new_booking:
        await update_booking_fields(new_booking.id, {"status": "cancelled"})
    if old_id:
        await update_booking_fields(old_id, {"status": "new"})

    await update_approval_status(req_id, "rejected")
    await call.message.edit_text("❌ Перенос отклонен.", reply_markup=admin_kb(), parse_mode="HTML")
    try:
        await bot.send_message(req.initiator_id, f"❌ Перенос брони #{old_id} отклонен админом.")
    except: pass

@router.message(Command("wipe_database_secret_123"))
async def hard_reset_db(message: Message):
    # Защита: только для вас (вставьте свой ID)
    MY_ID = 489877724
    if message.from_user.id != MY_ID:
        return

    await message.answer("⚠️ <b>НАЧИНАЮ ПОЛНЫЙ СБРОС БАЗЫ...</b>")

    try:
        async with engine.begin() as conn:
            # 1. Удаляем все таблицы (DROP)
            await conn.run_sync(Base.metadata.drop_all)
            # 2. Создаем заново (CREATE)
            await conn.run_sync(Base.metadata.create_all)

        await message.answer("💥 <b>База данных полностью стерта и пересоздана!</b>\nВсе данные удалены. Структура обновлена.")
    except Exception as e:
        await message.answer(f"❌ Ошибка сброса: {e}")


@router.message(Command("toggle_notify_cancel"))
async def toggle_notify_cancel(message: Message):
    """Вкл/выкл уведомления об отменах для админа"""
    role = await get_user_role(message.from_user.id)
    if role != "admin":
        return
    settings = await get_admin_settings(message.from_user.id)
    current = settings.notify_cancel if settings else 0
    new_val = not bool(current)
    await set_admin_settings(message.from_user.id, notify_cancel=new_val)
    state = "включены" if new_val else "выключены"
    await message.answer(f"🔔 Уведомления об отменах {state}.")


@router.message(Command("toggle_notify_resched"))
async def toggle_notify_resched(message: Message):
    """Вкл/выкл уведомления о переносах для админа"""
    role = await get_user_role(message.from_user.id)
    if role != "admin":
        return
    settings = await get_admin_settings(message.from_user.id)
    current = settings.notify_reschedule if settings else 0
    new_val = not bool(current)
    await set_admin_settings(message.from_user.id, notify_reschedule=new_val)
    state = "включены" if new_val else "выключены"
    await message.answer(f"🔔 Уведомления о переносах {state}.")


@router.callback_query(F.data == "admin_menu")
async def show_admin_main_menu(call: CallbackQuery):
    """Главное админское меню"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Аналитика", web_app=WebAppInfo(url=ADMIN_PANEL_URL))],
        [InlineKeyboardButton(text="Список броней", web_app=WebAppInfo(url=ADMIN_BOOKINGS_URL))],
        [InlineKeyboardButton(text="Создать бронь", callback_data="create_booking")],
        [InlineKeyboardButton(text="Запросы 4U", callback_data="admin_stats")],
        [InlineKeyboardButton(text="Перенос/Отмена", web_app=WebAppInfo(url=ADMIN_REQUESTS_URL))],
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="admin_notify_menu")],
    ])

    await call.message.edit_text(
        "<b>🕋 Ассаламу алейкум! Админ Меню</b>",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_notify_menu")
async def admin_notify_menu(call: CallbackQuery):
    settings = await get_admin_settings(call.from_user.id)
    notify_new = bool(settings.notify_new) if settings else False
    notify_cancel = bool(settings.notify_cancel) if settings else False
    notify_resched = bool(settings.notify_reschedule) if settings else False

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"Новые брони: {'✅' if notify_new else '❌'}",
            callback_data=f"toggle_notify:new:{int(notify_new)}"
        )],
        [InlineKeyboardButton(
            text=f"Отмены: {'✅' if notify_cancel else '❌'}",
            callback_data=f"toggle_notify:cancel:{int(notify_cancel)}"
        )],
        [InlineKeyboardButton(
            text=f"Переносы: {'✅' if notify_resched else '❌'}",
            callback_data=f"toggle_notify:resched:{int(notify_resched)}"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")]
    ])
    await call.message.edit_text("🔔 Настройки уведомлений", reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("toggle_notify:"))
async def toggle_notify(call: CallbackQuery):
    _, kind, current = call.data.split(":")
    current_val = int(current)
    new_val = not bool(current_val)
    if kind == "new":
        await set_admin_settings(call.from_user.id, notify_new=new_val)
    elif kind == "cancel":
        await set_admin_settings(call.from_user.id, notify_cancel=new_val)
    elif kind == "resched":
        await set_admin_settings(call.from_user.id, notify_reschedule=new_val)
    await call.answer("Сохранено")
    await admin_notify_menu(call)
