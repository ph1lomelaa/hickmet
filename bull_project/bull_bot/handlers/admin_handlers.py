from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder # 🔥
from contextlib import suppress
from aiogram.exceptions import TelegramBadRequest

from bull_project.bull_bot.core.google_sheets.four_u_logic import find_availability_for_4u, create_4u_sheet
from bull_project.bull_bot.database.models import Base
from bull_project.bull_bot.database.requests import get_active_4u_requests, get_4u_request_by_id, update_4u_status
from bull_project.bull_bot.config.keyboards import admin_kb
from bull_project.bull_bot.config.constants import bot
from bull_project.bull_bot.database.setup import engine

router = Router()

# === ССЫЛКИ НА АДМИН WEBAPP ===
# TODO: Разместите файлы на GitHub Pages или другом хостинге
ADMIN_PANEL_URL = "https://ph1lomelaa.github.io/book/admin-panel.html"
ADMIN_BOOKINGS_URL = "https://ph1lomelaa.github.io/book/admin-bookings.html"
ADMIN_CREATE_URL = "https://ph1lomelaa.github.io/book/admin-create-booking.html"

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


@router.callback_query(F.data == "admin_menu")
async def show_admin_main_menu(call: CallbackQuery):
    """Главное админское меню"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Аналитика", web_app=WebAppInfo(url=ADMIN_PANEL_URL))],
        [InlineKeyboardButton(text="Список броней", web_app=WebAppInfo(url=ADMIN_BOOKINGS_URL))],
        [InlineKeyboardButton(text="Создать бронь", callback_data="create_booking")],
        [InlineKeyboardButton(text="Запросы 4U", callback_data="admin_stats")],
    ])

    await call.message.edit_text(
        "<b>🕋 Ассаламу алейкум! Админ Меню</b>",
        reply_markup=kb,
        parse_mode="HTML"
    )
