import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest
from contextlib import suppress

# Импорты
from bull_project.bull_bot.database.requests import (
    search_tourist_by_name,
    get_all_bookings_in_package,
    get_db_packages_list,
    get_booking_by_id
)
from bull_project.bull_bot.core.google_sheets.client import (
    get_accessible_tables, get_sheet_names
)
from bull_project.bull_bot.config.keyboards import (
    get_menu_by_role, kb_select_table, kb_select_sheet, care_kb
)

router = Router()

class CareFlow(StatesGroup):
    waiting_search_query = State()
    choosing_table = State()
    choosing_sheet = State()
    choosing_pkg = State()

# ==================== 🔍 1. ПОИСК ТУРИСТА ====================

@router.callback_query(F.data == "care_search")
async def start_search(call: CallbackQuery, state: FSMContext):
    # Удаляем старое меню, чтобы не мусорить
    with suppress(TelegramBadRequest):
        await call.message.delete()

    await call.message.answer(
        "🔎 <b>Поиск туриста</b>\n\n"
        "Напишите Фамилию или Имя (можно частично):\n"
        "<i>Например: Zubanov или Зубанов</i>",
        parse_mode="HTML"
    )
    await state.set_state(CareFlow.waiting_search_query)
    await call.answer()

@router.message(CareFlow.waiting_search_query)
async def process_search(message: Message, state: FSMContext):
    query = message.text.strip()
    results = await search_tourist_by_name(query)

    if not results:
        await message.answer("❌ Никого не нашел. Попробуйте по-другому.", reply_markup=care_kb())
        await state.clear()
        return

    # Если нашли одного - сразу показываем карточку
    if len(results) == 1:
        b = results[0]
        await show_tourist_card(message, b)
        await state.clear()
    else:
        # Если много - даем кнопки
        kb = []
        for b in results:
            btn_text = f"{b.guest_last_name} {b.guest_first_name} | {b.package_name[:10]}..."
            kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"care_view:{b.id}")])

        await message.answer(
            f"🔎 Найдено {len(results)} туристов. Выберите:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
        )
        await state.clear()

@router.callback_query(F.data.startswith("care_view:"))
async def view_specific_tourist(call: CallbackQuery):
    bid = int(call.data.split(":")[1])
    b = await get_booking_by_id(bid)

    # Удаляем меню выбора
    with suppress(TelegramBadRequest):
        await call.message.delete()

    if b:
        await show_tourist_card(call.message, b)
    else:
        await call.answer("Бронь не найдена", show_alert=True)
        # Если не нашли, вернем меню
        await call.message.answer("👋 Меню Заботы", reply_markup=care_kb())

    await call.answer()

async def show_tourist_card(message: Message, b):
    """
    Показывает карточку.
    ЕСЛИ есть фото паспорта -> Шлет фото с описанием.
    ЕСЛИ нет -> Шлет текст.
    """
    # Формируем текст (Манифест)
    text = (
        f"👤 <b>{b.guest_last_name} {b.guest_first_name}</b>\n"
        f"──────────────────\n"
        f"📞 <b>ТЕЛЕФОН:</b> <code>{b.client_phone}</code>\n"
        f"──────────────────\n"
        f"🛂 Паспорт: {b.passport_num} (до {b.passport_expiry})\n"
        f"📅 Пакет: {b.package_name}\n"
        f"📍 Дата: {b.sheet_name}\n"
        f"🏨 Номер: {b.room_type} | 🍽 Питание: {b.meal_type}\n"
        f"👤 Менеджер: {b.manager_name_text}\n"
        f"📝 Коммент: {b.comment}\n"
        f"🚆 Поезд: {b.train}"
    )

    bk = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="care_menu")]])

    # 🔥 ПРОВЕРКА ФОТО
    if b.passport_image_path and os.path.exists(b.passport_image_path):
        try:
            photo = FSInputFile(b.passport_image_path)
            # Отправляем фото
            await message.answer_photo(photo, caption=text, reply_markup=bk, parse_mode="HTML")
            return
        except Exception as e:
            print(f"Ошибка отправки фото: {e}")

    # Фолбэк: Отправляем просто текст
    await message.answer(text, reply_markup=bk, parse_mode="HTML")

# ==================== 📞 2. СБОР ТЕЛЕФОНОВ ====================

@router.callback_query(F.data == "care_phones")
async def start_phones(call: CallbackQuery, state: FSMContext):
    # Удаляем старое, шлем новое
    with suppress(TelegramBadRequest):
        await call.message.delete()

    tables = get_accessible_tables()
    await call.message.answer("📅 <b>Выберите таблицу (Месяц):</b>", reply_markup=kb_select_table(tables), parse_mode="HTML")
    await state.set_state(CareFlow.choosing_table)
    await call.answer()

@router.callback_query(CareFlow.choosing_table, F.data.startswith("sel_tab:"))
async def care_sel_table(call: CallbackQuery, state: FSMContext):
    sid = call.data.split(":")[1]
    await state.update_data(current_sheet_id=sid)
    sheets = get_sheet_names(sid)

    await call.message.edit_text("✈️ <b>Выберите Лист (Дату):</b>", reply_markup=kb_select_sheet(sheets[:15], len(sheets)>15), parse_mode="HTML")
    await state.set_state(CareFlow.choosing_sheet)

@router.callback_query(CareFlow.choosing_sheet, F.data.startswith("sel_date:"))
async def care_sel_date(call: CallbackQuery, state: FSMContext):
    sname = call.data.split(":")[1]
    await state.update_data(current_sheet_name=sname)
    data = await state.get_data()

    packages = await get_db_packages_list(data['current_sheet_id'], sname)

    if not packages:
        await call.message.edit_text("❌ В этой дате нет активных броней в базе.", reply_markup=care_kb())
        await state.clear()
        return

    kb = []
    for pkg in packages:
        if not pkg: continue
        kb.append([InlineKeyboardButton(text=f"📦 {pkg[:30]}", callback_data=f"care_pkg:{pkg[:30]}")])

    await state.update_data(available_packages=packages)

    await call.message.edit_text("📦 <b>Выберите Пакет для списка:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await state.set_state(CareFlow.choosing_pkg)

@router.callback_query(CareFlow.choosing_pkg, F.data.startswith("care_pkg:"))
async def show_phone_list(call: CallbackQuery, state: FSMContext):
    pkg_short = call.data.split(":")[1]
    data = await state.get_data()

    full_pkg_name = next((p for p in data['available_packages'] if p.startswith(pkg_short)), pkg_short)

    bookings = await get_all_bookings_in_package(data['current_sheet_id'], data['current_sheet_name'], full_pkg_name)

    if not bookings:
        await call.answer("Пусто", show_alert=True)
        return

    report = f"📋 <b>СПИСОК ТУРИСТОВ</b>\n📦 {full_pkg_name}\n📅 {data['current_sheet_name']}\n\n"

    for i, b in enumerate(bookings, 1):
        phone = b.client_phone if b.client_phone else "❌ Нет номера"
        report += f"{i}. <b>{b.guest_last_name} {b.guest_first_name}</b>\n   📞 <code>{phone}</code>\n"

    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="care_menu")]])

    # Удаляем кнопки выбора пакета и шлем новый отчет
    with suppress(TelegramBadRequest):
        await call.message.delete()

    if len(report) > 4000:
        await call.message.answer(report[:4000], parse_mode="HTML")
        await call.message.answer(report[4000:], parse_mode="HTML", reply_markup=back_kb)
    else:
        await call.message.answer(report, reply_markup=back_kb, parse_mode="HTML")

    await state.clear()
    await call.answer()

@router.callback_query(F.data == "care_menu")
async def care_home(call: CallbackQuery, state: FSMContext):
    await state.clear()
    with suppress(TelegramBadRequest):
        await call.message.delete()
    await call.message.answer("🤝 <b>Ассаламу алейкум! Отдел Заботы</b>", reply_markup=care_kb(), parse_mode="HTML")
    await call.answer()