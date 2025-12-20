import html
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder # 🔥 ВАЖНО
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from datetime import datetime, date

from bull_project.bull_bot.database.requests import (
    get_all_managers_list,
    get_bookings_by_manager_date_range,
    get_bookings_by_package_full,
    get_last_n_bookings_by_manager,
    get_all_bookings_by_period
)
from bull_project.bull_bot.core.google_sheets.client import (
    get_accessible_tables, get_sheet_names, get_packages_from_sheet
)
from bull_project.bull_bot.config.keyboards import kb_select_table, kb_select_sheet, kb_select_package, admin_kb

router = Router()

class AppFlow(StatesGroup):
    pkg_table = State()
    pkg_sheet = State()
    pkg_item = State()
    man_select = State()
    man_custom_period = State()
    global_period = State()

# === ГЛАВНОЕ МЕНЮ ЗАЯВОК ===
@router.callback_query(F.data == "admin_apps_menu")
async def show_apps_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()

    # Красивые кнопки
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 По Пакетам", callback_data="apps_by_pkg"),
         InlineKeyboardButton(text="👤 По Менеджерам", callback_data="app_by_man")],
        [InlineKeyboardButton(text="📅 Выбрать Период (Общий)", callback_data="app_global_period")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")]
    ])

    # Используем edit_text, чтобы не дублировать
    await call.message.edit_text("📂 <b>ЗАЯВКИ И БРОНИ</b>\nВыберите режим просмотра:", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "admin_menu")
async def back_to_main_admin(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("🌙 <b>Ассаламу алейкум! Меню Админа</b>", reply_markup=admin_kb(), parse_mode="HTML")

# ==================== 1. ОБЩИЙ ПЕРИОД ====================

@router.callback_query(F.data == "app_global_period")
async def ask_global_period(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "📅 <b>Введите дату или период:</b>\n"
        "• <code>05.12</code> (за день)\n"
        "• <code>01.12-10.12</code> (диапазон)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_apps_menu")]]),
        parse_mode="HTML"
    )
    await state.set_state(AppFlow.global_period)

@router.message(AppFlow.global_period)
async def show_global_period_report(message: Message, state: FSMContext):
    d1, d2 = parse_date_range(message.text)
    if not d1:
        await message.answer("⚠️ Неверный формат. Попробуйте (ДД.ММ):")
        return

    bookings = await get_all_bookings_by_period(d1, d2)
    header = f"📅 <b>ОТЧЕТ ЗА ПЕРИОД:</b> {d1.strftime('%d.%m')} - {d2.strftime('%d.%m')}\n📊 Всего: {len(bookings)}\n"
    await send_smart_report(message, header, bookings)
    await state.clear()

# ==================== 2. ПО МЕНЕДЖЕРУ (ИСПОЛЬЗУЕМ BUILDER) ====================

@router.callback_query(F.data == "app_by_man")
async def start_by_man(call: CallbackQuery, state: FSMContext):
    await state.clear()
    managers = await get_all_managers_list()

    if not managers:
        await call.message.edit_text("❌ Список менеджеров пуст.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_apps_menu")]]))
        return

    # 🔥 СТРОИМ КРАСИВУЮ СЕТКУ КНОПОК
    builder = InlineKeyboardBuilder()
    for m in managers:
        builder.button(text=f"👤 {m.full_name}", callback_data=f"sel_man:{m.telegram_id}")

    builder.adjust(2) # По 2 кнопки в ряд!
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_apps_menu"))

    await call.message.edit_text("👤 <b>Выберите менеджера:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(AppFlow.man_select)

@router.callback_query(AppFlow.man_select, F.data.startswith("sel_man:"))
async def show_last_10(call: CallbackQuery, state: FSMContext):
    man_id = int(call.data.split(":")[1])
    await state.update_data(target_man_id=man_id)

    bookings = await get_last_n_bookings_by_manager(man_id, 10)

    header = "👤 <b>ПОСЛЕДНИЕ 10 ЗАЯВОК:</b>\n"
    if not bookings: header += "📭 Заявок нет.\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Посмотреть за Период", callback_data="man_period_ask")],
        [InlineKeyboardButton(text="🔙 К списку менеджеров", callback_data="app_by_man")]
    ])

    # Отправляем через edit_text (если короткое) или смарт (если длинное)
    await send_smart_report(call, header, bookings, kb)

@router.callback_query(F.data == "man_period_ask")
async def ask_man_period(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📆 <b>Введите дату или период (ДД.ММ):</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="app_by_man")]]))
    await state.set_state(AppFlow.man_custom_period)

@router.message(AppFlow.man_custom_period)
async def show_man_period_report(message: Message, state: FSMContext):
    d1, d2 = parse_date_range(message.text)
    if not d1:
        await message.answer("⚠️ Неверный формат.")
        return

    data = await state.get_data()
    man_id = data['target_man_id']
    bookings = await get_bookings_by_manager_date_range(man_id, d1, d2)

    header = f"👤 <b>ОТЧЕТ ПО МЕНЕДЖЕРУ</b>\n📅 {d1.strftime('%d.%m')} - {d2.strftime('%d.%m')}\n📊 Всего: {len(bookings)}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К менеджеру", callback_data=f"sel_man:{man_id}")]])

    await send_smart_report(message, header, bookings, kb)

# ==================== 3. ПО ПАКЕТУ ====================

@router.callback_query(F.data == "apps_by_pkg")
async def start_by_pkg(call: CallbackQuery, state: FSMContext):
    await state.clear()
    tables = get_accessible_tables()
    await call.message.edit_text("📅 <b>Выберите таблицу:</b>", reply_markup=kb_select_table(tables), parse_mode="HTML")
    await state.set_state(AppFlow.pkg_table)

@router.callback_query(AppFlow.pkg_table, F.data.startswith("sel_tab:"))
async def admin_sel_tab(call: CallbackQuery, state: FSMContext):
    sid = call.data.split(":")[1]
    await state.update_data(current_sheet_id=sid)
    sheets = get_sheet_names(sid)
    await call.message.edit_text("✈️ <b>Выберите дату вылета:</b>", reply_markup=kb_select_sheet(sheets[:15], len(sheets)>15), parse_mode="HTML")
    await state.set_state(AppFlow.pkg_sheet)

@router.callback_query(AppFlow.pkg_sheet, F.data.startswith("sel_date:"))
async def admin_sel_date(call: CallbackQuery, state: FSMContext):
    sname = call.data.split(":")[1]
    await state.update_data(current_sheet_name=sname)
    data = await state.get_data()
    pkgs = get_packages_from_sheet(data['current_sheet_id'], sname)
    await state.update_data(packages_map=pkgs)
    await call.message.edit_text("📦 <b>Выберите пакет:</b>", reply_markup=kb_select_package(pkgs), parse_mode="HTML")
    await state.set_state(AppFlow.pkg_item)

@router.callback_query(AppFlow.pkg_item, F.data.startswith("sel_pkg:"))
async def admin_show_pkg_details(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    row_id = int(call.data.split(":")[1])
    pkg_name = data['packages_map'].get(row_id, "Unknown")

    bookings = await get_bookings_by_package_full(data['current_sheet_name'], pkg_name)

    header = f"📦 <b>ПАКЕТ: {pkg_name}</b>\n📅 {data['current_sheet_name']}\n📊 Всего: {len(bookings)}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать бронь здесь", callback_data="create_booking")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data=f"sel_date:{data['current_sheet_name']}")]
    ])

    await send_smart_report(call, header, bookings, kb)

# ==================== УМНАЯ ОТПРАВКА ====================

def clean(text):
    return html.escape(str(text)) if text else "-"

def format_single_booking(b):
    return (
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"<b>ФИО:</b> {clean(b.guest_last_name)} {clean(b.guest_first_name)}\n"
        f"<b>Дата вылета:</b> {clean(b.sheet_name)}\n"
        f"<b>Пакет:</b> {clean(b.package_name)}\n"
        f"<b>Сумма:</b> {clean(b.price)}\n"
        f"<b>Менеджер:</b> {clean(b.manager_name_text)}\n"
        f"<b>Тип номера:</b> {clean(b.room_type)}\n"
        f"📍 <b>Строка:</b> {clean(b.sheet_row_number)}\n"
    )

async def send_smart_report(message_or_call, header, bookings, kb=None):
    if not kb:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="admin_apps_menu")]])

    blocks = [header]
    for b in bookings:
        blocks.append(format_single_booking(b))

    chunk = ""
    # Определяем метод отправки
    is_call = isinstance(message_or_call, CallbackQuery)
    sender = message_or_call.message if is_call else message_or_call

    # Если блоков мало - редактируем существующее
    full_text = "\n".join(blocks)
    if len(full_text) < 4000:
        if is_call:
            await message_or_call.message.edit_text(full_text, reply_markup=kb, parse_mode="HTML")
        else:
            await sender.answer(full_text, reply_markup=kb, parse_mode="HTML")
        return

    # Если много - разбиваем и шлем новые
    if is_call: await message_or_call.message.delete()

    for block in blocks:
        if len(chunk) + len(block) > 4000:
            await sender.answer(chunk, parse_mode="HTML")
            chunk = ""
        chunk += block + "\n"

    await sender.answer(chunk, reply_markup=kb, parse_mode="HTML")

def parse_date_range(text):
    text = text.strip().replace("/", ".").replace(" ", "")
    current_year = datetime.now().year
    try:
        if "-" in text:
            d1_s, d2_s = text.split("-")
            d1 = datetime.strptime(f"{d1_s}.{current_year}", "%d.%m.%Y").date()
            d2 = datetime.strptime(f"{d2_s}.{current_year}", "%d.%m.%Y").date()
            if d1 > d2: d1, d2 = d2, d1
            return d1, d2
        else:
            d = datetime.strptime(f"{text}.{current_year}", "%d.%m.%Y").date()
            return d, d
    except:
        return None, None