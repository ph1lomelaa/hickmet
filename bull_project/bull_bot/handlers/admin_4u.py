from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bull_project.bull_bot.database.requests import (
    get_4u_request_by_id, update_4u_status, get_4u_request_by_id
)
from bull_project.bull_bot.core.google_sheets.four_u_logic import find_availability_for_4u, create_4u_sheet
from bull_project.bull_bot.config.constants import bot

router = Router()

class Admin4UFlow(StatesGroup):
    viewing_request = State()
    choosing_source = State() # Выбор пакета-донора

# === 1. ПРОСМОТР ЗАЯВКИ ===

@router.callback_query(F.data.startswith("view_4u:"))
async def admin_view_request(call: CallbackQuery, state: FSMContext):
    req_id = int(call.data.split(":")[1])
    req = await get_4u_request_by_id(req_id)

    if not req:
        await call.answer("Заявка не найдена")
        return

    status_emoji = "🔴" if req.status == 'pending' else ("🟢" if req.status == 'approved' else "⚫️")

    text = (
        f"📝 <b>ЗАЯВКА 4U #{req.id}</b>\n"
        f"👤 Менеджер: {req.manager_name}\n"
        f"📅 Даты: {req.dates}\n"
        f"👥 Людей: {req.pilgrim_count}\n"
        f"🛏 Номера: {req.room_type}\n"
        f"Статус: {status_emoji} {req.status}\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Проверить свободные места", callback_data=f"check_4u:{req_id}")],
        [InlineKeyboardButton(text="✅ Одобрить и Создать лист", callback_data=f"approve_4u_start:{req_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_4u:{req_id}")]
    ])

    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

# === 2. ПРОВЕРКА МЕСТ ===

@router.callback_query(F.data.startswith("check_4u:"))
async def check_availability(call: CallbackQuery):
    req_id = int(call.data.split(":")[1])
    req = await get_4u_request_by_id(req_id)

    await call.message.edit_text("⏳ <b>Сканирую таблицы...</b>\nЭто может занять 5-10 секунд.", parse_mode="HTML")

    # ВАЖНО: Тут нужно знать ID таблицы.
    # Либо мы ищем по всем таблицам, либо (лучше) храним ID "актуальной" таблицы в конфиге.
    # Допустим, мы берем ID из первой попавшейся активной таблицы или просим выбрать.
    # Для упрощения возьмем TABLE_ID из настроек (если он там один)
    # Или просто хардкод для теста, пока вы не сделаете выбор таблицы.
    TABLE_ID = "ВАШ_ID_ТАБЛИЦЫ"

    results = await find_availability_for_4u(TABLE_ID, req.dates, req.pilgrim_count, req.room_type)

    if not results:
        text = "🤷‍♂️ <b>Подходящих дырок не найдено.</b>\nПридется создавать лист с нуля или искать вручную."
    else:
        text = "🔎 <b>Найдено место в пакетах:</b>\n\n"
        for r in results:
            text += (
                f"📄 Лист: {r['sheet']}\n"
                f"📦 Пакет: {r['package']}\n"
                f"✅ Свободно: {r['free']} строк\n"
                f"⚠️ <b>Удалить строки: {r['rows_to_clear']}</b>\n"
                f"------------------\n"
            )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К заявке", callback_data=f"view_4u:{req_id}")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

# === 3. СОЗДАНИЕ ЛИСТА (ОДОБРЕНИЕ) ===

@router.callback_query(F.data.startswith("approve_4u_start:"))
async def start_approval(call: CallbackQuery, state: FSMContext):
    req_id = int(call.data.split(":")[1])
    # Тут можно спросить: "Откуда берем места?" (чтобы знать, рядом с каким листом ставить)
    # Но для упрощения можно просто спросить подтверждение.

    await state.update_data(req_id=req_id)

    # Выводим список найденных вариантов (еще раз, чтобы выбрать "донора")
    # ... (код сканирования повторно или кэширование) ...
    # Допустим, мы просто создаем лист.

    text = "🚀 <b>Создание листа 4U</b>\nВы уверены? Будет создан новый лист, я сделаю Merge ячеек."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 СОЗДАТЬ", callback_data="do_create_4u")],
        [InlineKeyboardButton(text="Отмена", callback_data=f"view_4u:{req_id}")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("do_create:"))
async def execute_creation(call: CallbackQuery): # Убрал state, если он не нужен для req_id
    req_id = int(call.data.split(":")[1])
    req = await get_4u_request_by_id(req_id)

    if not req:
        await call.answer("Заявка не найдена", show_alert=True)
        return

    await call.message.edit_text("⏳ <b>Работаю с Excel...</b>\nСоздаю лист, объединяю ячейки...", parse_mode="HTML")

    # Создаем лист
    success, result_msg = await create_4u_sheet(
        req.table_id, req.dates, req.pilgrim_count, req.room_type, req.manager_name
    )

    if success:
        # Обновляем статус в БД (передаем result_msg, а не result)
        await update_4u_status(req_id, "approved", result_msg)

        # Уведомляем менеджера
        try:
            await bot.send_message(
                req.manager_id,
                f"✅ <b>Ваша заявка 4U на {req.dates} одобрена!</b>\n"
                f"Создан лист: <code>{result_msg}</code>\n"
                f"Можете заносить людей."
            )
        except: pass

        await call.message.edit_text(
            f"✅ <b>Готово!</b>\nЛист <code>{result_msg}</code> создан.\nМенеджер уведомлен.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К списку", callback_data="admin_stats")]])
        )
    else:
        # Если ошибка, result_msg содержит текст ошибки
        await call.message.edit_text(f"❌ Ошибка: {result_msg}", parse_mode="HTML")