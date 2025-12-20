from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from datetime import datetime, timedelta, date

from bull_project.bull_bot.database.requests import get_detailed_stats_by_period
from bull_project.bull_bot.config.keyboards import admin_kb

router = Router()

class ReportFlow(StatesGroup):
    waiting_period = State()

# === ГЛАВНОЕ МЕНЮ ОТЧЕТОВ ===
@router.callback_query(F.data == "admin_reports_menu")
async def show_reports_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="За Сегодня", callback_data="rep:today")],
        [InlineKeyboardButton(text="За Неделю", callback_data="rep:week")],
        [InlineKeyboardButton(text="За Месяц", callback_data="rep:month")],
        [InlineKeyboardButton(text="📅 Выбрать период", callback_data="rep:custom")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")]
    ])
    await call.message.edit_text("📊 <b>ОТЧЕТЫ И СТАТИСТИКА</b>\nВыберите период:", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "admin_menu")
async def back_to_admin_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("🌙 <b>Ассаламу алейкум! Меню Админа</b>", reply_markup=admin_kb(), parse_mode="HTML")

# === БЫСТРЫЕ ПЕРИОДЫ ===
@router.callback_query(F.data.startswith("rep:"))
async def process_quick_report(call: CallbackQuery, state: FSMContext):
    mode = call.data.split(":")[1]
    today = datetime.now().date()

    if mode == "custom":
        await call.message.edit_text(
            "📅 <b>Введите период:</b>\n<code>01.12</code> (день) или <code>01.12-10.12</code> (диапазон)",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_reports_menu")]]),
            parse_mode="HTML"
        )
        await state.set_state(ReportFlow.waiting_period)
        return

    # Определяем даты
    d2 = today
    if mode == "today":
        d1 = today
    elif mode == "week":
        d1 = today - timedelta(days=7)
    elif mode == "month":
        d1 = today - timedelta(days=30)

    await generate_and_send_report(call.message, d1, d2, is_edit=True)

# === СВОЙ ПЕРИОД ===
@router.message(ReportFlow.waiting_period)
async def process_custom_report(message: Message, state: FSMContext):
    text = message.text.strip().replace("/", ".").replace(" ", "")
    current_year = datetime.now().year

    try:
        if "-" in text:
            d1_s, d2_s = text.split("-")
            d1 = datetime.strptime(f"{d1_s}.{current_year}", "%d.%m.%Y").date()
            d2 = datetime.strptime(f"{d2_s}.{current_year}", "%d.%m.%Y").date()
            if d1 > d2: d1, d2 = d2, d1
        else:
            d1 = datetime.strptime(f"{text}.{current_year}", "%d.%m.%Y").date()
            d2 = d1
    except:
        await message.answer("⚠️ Неверный формат даты.")
        return

    await generate_and_send_report(message, d1, d2, is_edit=False)
    await state.clear()

# === ГЕНЕРАТОР ОТЧЕТА (ТОП 10) ===
# (Импорты те же)
# ...

# === ГЕНЕРАТОР ОТЧЕТА ===
async def generate_and_send_report(message, d1, d2, is_edit=False):
    stats = await get_detailed_stats_by_period(d1, d2)

    text = (
        f"📊 <b>ОТЧЕТ ЗА ПЕРИОД:</b>\n"
        f"📅 {d1.strftime('%d.%m')} — {d2.strftime('%d.%m')}\n"
        f"──────────────────\n"
        f"🔥 <b>ВСЕГО ПРОДАЖ: {stats['total']}</b>\n\n"
    )

    text += "🏆 <b>ТОП-10 ПАКЕТОВ:</b>\n"
    if stats['top_packages']:
        for i, (name, cnt) in enumerate(stats['top_packages'], 1):
            text += f"{i}. {name} — <b>{cnt}</b>\n"
    else:
        text += "— Нет данных\n"

    text += "\n👤 <b>РЕЙТИНГ МЕНЕДЖЕРОВ:</b>\n"
    if stats['managers']:
        for name, cnt in stats['managers']:
            text += f"• {name}: <b>{cnt}</b>\n"
    else:
        text += "— Нет данных\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К отчетам", callback_data="admin_reports_menu")]])

    # Всегда отправляем новое сообщение, если это длинный отчет, чтобы не сбивать разметку
    # Или редактируем, если короткий
    if is_edit and isinstance(message, Message):
        if len(text) < 4000:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.delete() # Удаляем старое меню
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")