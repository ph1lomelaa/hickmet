import os
import json
import urllib.parse
import time
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from pytesseract.pytesseract import LOGGER
from contextlib import suppress

# --- ИМПОРТЫ ПРОЕКТА ---
from bull_project.bull_bot.config.constants import (
    ABS_UPLOADS_DIR, bot, POPPLER_PATH,
    ADMIN_PASSWORD, MANAGER_PASSWORD, CARE_PASSWORD,
    API_BASE_URL
)
from bull_project.bull_bot.config.keyboards import (
    cancel_kb, get_menu_by_role, main_menu_kb, manager_kb
)
from bull_project.bull_bot.core.parsers.passport_parser import PassportParser, PassportParserEasyOCR
from bull_project.bull_bot.database.requests import (
    add_user, get_user_role, add_booking_to_db, add_4u_request, get_admin_ids,
    update_booking_row, delete_user, get_user_by_id, get_booking_by_id, mark_booking_cancelled
)
from bull_project.bull_bot.core.google_sheets.writer import save_group_booking, clear_booking_in_sheets

router = Router()

# Ссылка на твой фронтенд
WEB_APP_URL = "https://ph1lomelaa.github.io/book/index.html"

# ==================== ПОЛНЫЙ КЛАСС СОСТОЯНИЙ (FSM) ====================
class BookingFlow(StatesGroup):
    waiting_access_code = State()
    waiting_registration_name = State()

    # Выбор таблицы/даты/пакета (для переноса и создания брони)
    choosing_table = State()
    choosing_date = State()
    choosing_pkg = State()

    # Сбор паломников
    waiting_count = State()
    waiting_passport = State()
    waiting_manual_name = State()

    # Состояние ожидания данных из формы (ОБЯЗАТЕЛЬНО!)
    waiting_web_app_data = State()

    # Для запросов 4U
    waiting_4u_dates = State()
    waiting_4u_count = State()
    waiting_4u_room = State()

def ensure_uploads_dir():
    os.makedirs(ABS_UPLOADS_DIR, exist_ok=True)

# ==================== 1. ВХОД / РЕГИСТРАЦИЯ / LOGOUT ====================

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user_by_id(message.from_user.id)
    if user and user.role != "guest":
        await message.answer(f"🕋 <b>Ассаламу алейкум, {user.full_name}!</b>",
                             reply_markup=get_menu_by_role(user.role), parse_mode="HTML")
    else:
        await message.answer("🕋 <b>Ассаламу алейкум!</b>\nВведите Код Доступа для регистрации:", parse_mode="HTML")
        await state.set_state(BookingFlow.waiting_access_code)

@router.message(Command("logout"))
async def cmd_logout(message: Message, state: FSMContext):
    await delete_user(message.from_user.id)
    await state.clear()
    print(f"👤 [LOGOUT] Пользователь {message.from_user.id} удален.")
    await message.answer("👋 Вы вышли из системы. Введите код для регистрации:")
    await state.set_state(BookingFlow.waiting_access_code)

@router.message(BookingFlow.waiting_access_code)
async def check_code(message: Message, state: FSMContext):
    code = message.text.strip()
    role = "admin" if code == ADMIN_PASSWORD else "care" if code == CARE_PASSWORD else "manager" if code == MANAGER_PASSWORD else None
    if role:
        await state.update_data(reg_role=role)
        await message.answer("✅ Код принят! <b>Как вас зовут?</b>", parse_mode="HTML")
        await state.set_state(BookingFlow.waiting_registration_name)
    else: await message.answer("❌ Неверный код.")

@router.message(BookingFlow.waiting_registration_name)
async def register_name(message: Message, state: FSMContext):
    name = message.text.strip()
    role = (await state.get_data()).get("reg_role", "manager")
    await add_user(message.from_user.id, name, message.from_user.username, role=role)
    await message.answer(f"🕋 Ассаламу алейкум, {name}!", reply_markup=get_menu_by_role(role))
    await state.clear()

# ==================== 2. СБОР ПАСПОРТОВ ====================

@router.callback_query(F.data == "create_booking")
async def start_booking(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('is_reschedule'): await state.clear()
    await call.message.answer("Сколько паломников? (Число):", parse_mode="HTML")
    await state.set_state(BookingFlow.waiting_count)

@router.message(BookingFlow.waiting_count)
async def input_count(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Введите число (например: 2).")
        return
    await state.update_data(total_pilgrims=int(message.text), current_pilgrim=1, pilgrims_list=[])
    await message.answer(
        "📤 Отправьте паспорт 1-го паломника\n\n"
        "💡 <i>Если нет паспорта, напишите текстом:\n"
        "ФАМИЛИЯ ИМЯ</i>",
        parse_mode="HTML"
    )
    await state.set_state(BookingFlow.waiting_passport)

# В функции process_passport (строка ~100)

PARSER_ENGINE = os.getenv("PASSPORT_ENGINE", "tesseract").lower()

def create_passport_parser(debug=False, save_ocr=False):
    if PARSER_ENGINE == "easyocr":
        return PassportParserEasyOCR(POPPLER_PATH, debug=debug)
    return PassportParser(POPPLER_PATH, debug=debug, save_ocr=save_ocr)


@router.message(BookingFlow.waiting_passport, F.document | F.photo)
async def process_passport(message: Message, state: FSMContext):
    ensure_uploads_dir()
    data = await state.get_data()
    curr = data.get('current_pilgrim', 1)
    fid = message.document.file_id if message.document else message.photo[-1].file_id
    ext = os.path.splitext(message.document.file_name)[1] if message.document and message.document.file_name else ".jpg"
    temp_path = os.path.join(ABS_UPLOADS_DIR, f"{message.from_user.id}_p{curr}_temp{ext}")

    # Сначала загружаем во временный файл
    await bot.download_file((await bot.get_file(fid)).file_path, temp_path)
    print(f"📥 Файл загружен: {temp_path}")

    # Конвертируем в PNG (итоговый путь всегда .png)
    png_path = os.path.join(ABS_UPLOADS_DIR, f"{message.from_user.id}_p{curr}.png")

    try:
        from pdf2image import convert_from_path
        from PIL import Image

        if temp_path.lower().endswith('.pdf'):
            # Конвертируем PDF в PNG
            print(f"🔄 Конвертация PDF в PNG...")
            pages = convert_from_path(temp_path, dpi=300, poppler_path=POPPLER_PATH)
            if pages:
                pages[0].save(png_path, 'PNG')
                print(f"✅ PDF сконвертирован в PNG: {png_path}")
            else:
                raise Exception("Не удалось конвертировать PDF")
        else:
            # Если это изображение, просто конвертируем в PNG
            img = Image.open(temp_path)
            img.save(png_path, 'PNG')
            print(f"✅ Изображение сохранено как PNG: {png_path}")

        # Удаляем временный файл
        if os.path.exists(temp_path):
            os.remove(temp_path)

        path = png_path  # Используем PNG путь
        print(f"📸 Паспорт сохранен в PNG: {path}")

    except Exception as e:
        print(f"⚠️ Ошибка конвертации, используем оригинал: {e}")
        path = temp_path

    msg = await message.answer("⏳ Читаю данные... (это может занять до 30 сек)\n\n💡 Если долго - можете ввести данные вручную")

    try:
        import asyncio

        # 🔥 ТАЙМАУТ: Даем OCR максимум 30 секунд
        async def parse_with_timeout():
            parser = create_passport_parser(debug=(curr <= 3), save_ocr=True)
            # Запускаем парсинг в отдельном потоке (parser.parse блокирующая функция)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, parser.parse, path)

        try:
            passport_result = await asyncio.wait_for(parse_with_timeout(), timeout=30.0)
        except asyncio.TimeoutError:
            print(f"⏱️ OCR превысил таймаут 30 секунд")
            with suppress(Exception):
                await msg.delete()
            await state.update_data(temp_p={'passport_image_path': path})
            await message.answer(
                "⏱️ <b>Распознавание заняло слишком много времени</b>\n\n"
                "Пожалуйста, введите <b>Фамилию и Имя</b> вручную:",
                parse_mode="HTML"
            )
            await state.set_state(BookingFlow.waiting_manual_name)
            return

        # 🔥 ИСПРАВЛЕНИЕ: Используем to_dict() для получения всех полей
        p_data = passport_result.to_dict()
        p_data['passport_image_path'] = path  # временно локальный путь

        # Парсер уже выбрал лучшие данные внутри метода parse()
        # Не перезаписываем их данными из MRZ

        # 🔥 КРИТИЧНО: Добавляем snake_case поля для writer.py
        p_data['last_name'] = p_data.get('Last Name', '-')
        p_data['first_name'] = p_data.get('First Name', '-')
        p_data['gender'] = p_data.get('Gender', 'M')
        p_data['dob'] = p_data.get('Date of Birth', '-')
        p_data['doc_num'] = p_data.get('Document Number', '-')
        p_data['doc_exp'] = p_data.get('Document Expiration', '-')
        p_data['iin'] = p_data.get('IIN', '-')

        # Логирование для проверки
        print(f"\n{'='*60}")
        print(f"📋 ИТОГОВЫЕ ДАННЫЕ ПАСПОРТА (паломник {curr}):")
        print(f"{'='*60}")
        print(f"  👤 Фамилия (Last Name):      {p_data.get('Last Name', 'НЕТ')}")
        print(f"  👤 Имя (First Name):         {p_data.get('First Name', 'НЕТ')}")
        print(f"  👥 Пол (Gender):             {p_data.get('Gender', 'НЕТ')}")
        print(f"  🎂 Дата рождения (DOB):      {p_data.get('Date of Birth', 'НЕТ')}")
        print(f"  📄 Номер паспорта:           {p_data.get('Document Number', 'НЕТ')}")
        print(f"  🆔 ИИН:                      {p_data.get('IIN', 'НЕТ')}")
        print(f"  📅 Срок действия:            {p_data.get('Document Expiration', 'НЕТ')}")
        print(f"  📸 Путь к файлу:             {path}")
        print(f"{'='*60}\n")

        # Загружаем файл на API, если указан API_BASE_URL
        if API_BASE_URL:
            try:
                upload_url = f"{API_BASE_URL}/api/passports/upload"
                async with aiohttp.ClientSession() as session:
                    with open(path, "rb") as f:
                        form = aiohttp.FormData()
                        form.add_field("file", f, filename=os.path.basename(path))
                        resp = await session.post(upload_url, data=form)
                        res_json = await resp.json()
                        if resp.status == 200 and res_json.get("ok") and res_json.get("path"):
                            p_data['passport_image_path'] = res_json["path"]
                            print(f"✅ Паспорт загружен на API: {res_json['path']}")
                        else:
                            print(f"⚠️ Не удалось загрузить паспорт на API: status={resp.status}, res={res_json}")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки на API: {e}")

        with suppress(Exception):
            await msg.delete()

        # 🔥 ПРОВЕРКА КАЧЕСТВА РАСПОЗНАВАНИЯ
        last_name = p_data.get('Last Name', '').strip()
        first_name = p_data.get('First Name', '').strip()

        # Проверяем качество распознавания
        needs_manual_entry = False
        reason = ""

        if not last_name or len(last_name) < 2:
            needs_manual_entry = True
            reason = "Фамилия не распознана или слишком короткая"
        elif not first_name or len(first_name) < 2:
            needs_manual_entry = True
            reason = "Имя не распознано или слишком короткое"
        # Проверяем на слишком много спецсимволов (признак плохого OCR)
        elif sum(not c.isalnum() and not c.isspace() for c in last_name) > len(last_name) * 0.3:
            needs_manual_entry = True
            reason = "Фамилия содержит много спецсимволов (плохое качество OCR)"
        elif sum(not c.isalnum() and not c.isspace() for c in first_name) > len(first_name) * 0.3:
            needs_manual_entry = True
            reason = "Имя содержит много спецсимволов (плохое качество OCR)"

        if needs_manual_entry:
            print(f"⚠️ Требуется ручной ввод: {reason}")
            print(f"   Last Name: '{last_name}'")
            print(f"   First Name: '{first_name}'")
            await state.update_data(temp_p=p_data)
            await message.answer(
                f"⚠️ <b>{reason}</b>\n\n"
                "Пожалуйста, введите <b>Фамилию и Имя</b> вручную:",
                parse_mode="HTML"
            )
            await state.set_state(BookingFlow.waiting_manual_name)
        else:
            await next_step_pilgrim(message, state, p_data)

    except Exception as e:
        print(f"❌ Ошибка парсинга: {e}")
        import traceback
        traceback.print_exc()

        with suppress(Exception):
            await msg.delete()
        await state.update_data(temp_p={'passport_image_path': path})
        await message.answer("⚠️ Ошибка OCR. Введите Фамилию Имя:")
        await state.set_state(BookingFlow.waiting_manual_name)

@router.message(BookingFlow.waiting_passport, F.text)
async def process_passport_text(message: Message, state: FSMContext):
    """Обработка текстового ввода имени вместо паспорта"""
    data = await state.get_data()
    curr = data.get('current_pilgrim', 1)

    # Парсим фамилию и имя из текста
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer(
            "❌ Введите Фамилию и Имя через пробел\n\n"
            "Например: <b>IVANOV IVAN</b>\n\n"
            "Или отправьте фото/скан паспорта",
            parse_mode="HTML"
        )
        return

    last_name = parts[0].upper()
    first_name = " ".join(parts[1:]).upper()

    # Создаем минимальный набор данных паспорта
    p_data = {
        'Last Name': last_name,
        'First Name': first_name,
        'Gender': 'M',  # По умолчанию, можно будет изменить в форме
        'Date of Birth': '-',
        'Document Number': '-',
        'Document Expiration': '-',
        'IIN': '-',
        'passport_image_path': None,  # Нет паспорта
        # Snake_case поля для writer.py
        'last_name': last_name,
        'first_name': first_name,
        'gender': 'M',
        'dob': '-',
        'doc_num': '-',
        'doc_exp': '-',
        'iin': '-',
    }

    print(f"\n{'='*60}")
    print(f"✍️ ТЕКСТОВЫЙ ВВОД (паломник {curr}):")
    print(f"{'='*60}")
    print(f"  👤 Фамилия: {last_name}")
    print(f"  👤 Имя: {first_name}")
    print(f"  📸 Паспорт: НЕТ (введено вручную)")
    print(f"{'='*60}\n")

    await message.answer(
        f"✅ Принято: <b>{last_name} {first_name}</b>\n\n"
        "⚠️ Остальные данные (дата рождения, паспорт) нужно будет заполнить в форме",
        parse_mode="HTML"
    )

    await next_step_pilgrim(message, state, p_data)

@router.message(BookingFlow.waiting_manual_name)
async def manual_name(message: Message, state: FSMContext):
    parts = message.text.split()
    if len(parts) < 2: return
    data = await state.get_data()
    p = data.get('temp_p', {})
    p['Last Name'], p['First Name'] = parts[0].upper(), " ".join(parts[1:]).upper()
    await next_step_pilgrim(message, state, p)

async def next_step_pilgrim(message: Message, state: FSMContext, p_data):
    data = await state.get_data()
    pilgrims = data.get('pilgrims_list', [])
    pilgrims.append(p_data)
    await state.update_data(pilgrims_list=pilgrims)

    if data['current_pilgrim'] < data['total_pilgrims']:
        await state.update_data(current_pilgrim=data['current_pilgrim'] + 1)
        next_num = data['current_pilgrim'] + 1
        await message.answer(
            f"✅ Ок. Паспорт <b>{next_num}-го</b> паломника:\n\n"
            f"💡 <i>Можно отправить фото паспорта или написать текстом:\n"
            f"ФАМИЛИЯ ИМЯ</i>",
            parse_mode="HTML"
        )
        await state.set_state(BookingFlow.waiting_passport)
    else:
        await send_webapp_link(message, state)

# В функции send_webapp_link (строка ~145)

async def send_webapp_link(message: Message, state: FSMContext):
    data = await state.get_data()
    pilgrims = data.get('pilgrims_list', [])

    # 🔥 ИСПРАВЛЕНИЕ: Если это перенос и список пуст, восстанавливаем из reschedule_passport
    if (not pilgrims) and data.get("is_reschedule") and data.get("reschedule_passport"):
        pilgrims = [data.get("reschedule_passport")]
        await state.update_data(pilgrims_list=pilgrims, total_pilgrims=len(pilgrims))
        print(f"✅ Восстановлен паломник для переноса: {pilgrims[0].get('Last Name', '?')}")

    # ДЕБАГ: Логирование для переноса
    print(f"\n{'='*60}")
    print(f"📤 ОТПРАВКА В WEBAPP (send_webapp_link)")
    print(f"{'='*60}")
    print(f"  is_reschedule: {data.get('is_reschedule', False)}")
    print(f"  old_booking_id: {data.get('old_booking_id', 'НЕТ')}")
    print(f"  Количество паломников: {len(pilgrims)}")
    print(f"  pilgrims_list present: {bool(pilgrims)}")
    if pilgrims:
        for i, p in enumerate(pilgrims):
            print(f"  Паломник {i+1}: {p.get('Last Name', '?')} {p.get('First Name', '?')}")
    print(f"{'='*60}\n")

    if not pilgrims:
        await message.answer("❌ Ошибка: список паломников пуст. Начните бронирование заново.")
        await state.clear()
        return

    # 🔥 ИСПРАВЛЕНИЕ: Передаем ПОЛНЫЕ данные паспорта включая путь к фото
    p_full_data = []
    for p in pilgrims:
        p_full_data.append({
            "name": f"{p.get('Last Name', '-')} {p.get('First Name', '-')}",
            "last_name": p.get('Last Name', '-'),
            "first_name": p.get('First Name', '-'),
            "gender": p.get('Gender', 'M'),
            "date_of_birth": p.get('Date of Birth', '-'),
            "passport_num": p.get('Document Number', '-'),
            "passport_expiry": p.get('Document Expiration', '-'),
            "iin": p.get('IIN', '-'),
            "phone": p.get('client_phone', '-'),
            "passport_image_path": p.get('passport_image_path', None)
        })

    # Логирование для проверки
    print(f"📤 ОТПРАВКА В WEBAPP:")
    for i, p in enumerate(p_full_data):
        print(f"  Паломник {i+1}:")
        print(f"    Имя: {p.get('first_name')}")
        print(f"    Фамилия: {p.get('last_name')}")
        print(f"    Путь к паспорту: {p.get('passport_image_path')}")

    params = {"pilgrims": json.dumps(p_full_data, ensure_ascii=False)}
    url = f"{WEB_APP_URL}?{urllib.parse.urlencode(params)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Заполнить форму", web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton(text="Запрос 4U", callback_data="req_4u")],
    ])

    await message.answer("Паспорта собраны! Выберите действие:", reply_markup=kb)
    await state.set_state(BookingFlow.waiting_web_app_data)

# ==================== 3. ПРИЕМ JSON И ЗАПИСЬ (ФИНАЛ) ====================
# ... (твои импорты) ...
from bull_project.bull_bot.database.requests import add_booking_to_db, update_booking_row

@router.message(F.web_app_data)
async def handle_webapp_data(message: Message, state: FSMContext):
    import json
    form = json.loads(message.web_app_data.data)  # данные из WebApp

    # Проверяем, это новая автономная Web App или старая форма
    if form.get("action") == "booking_completed":
        # Это событие от новой Web App (index.html)
        await message.answer("✅ Бронь успешно создана!")

        # Возвращаем в главное меню
        user_id = message.from_user.id
        role = await get_user_role(user_id)
        menu_kb = get_menu_by_role(role)

        await message.answer(
            "<b>🕋 Главное меню</b>",
            reply_markup=menu_kb,
            parse_mode="HTML"
        )
        await state.clear()
        return

    # Старая логика для формы с FSM
    data = await state.get_data()
    pilgrims = data.get("pilgrims_list", [])
    # Если это перенос и список не проставлен, пробуем взять сохраненный паспорт
    if (not pilgrims) and data.get("is_reschedule") and data.get("reschedule_passport"):
        pilgrims = [data.get("reschedule_passport")]
        await state.update_data(pilgrims_list=pilgrims, total_pilgrims=len(pilgrims))

    if not pilgrims:
        await message.answer("⚠️ Не нашёл список паломников в состоянии. Начните бронирование заново.")
        await state.clear()
        return

    # 1) Телефоны из формы раскидываем по паломникам
    phones = form.get("phones", [])
    for i, p in enumerate(pilgrims):
        if i < len(phones):
            p["client_phone"] = phones[i]

    # 2) Общие поля (для всех одинаковые)
    common = {
        "table_id": form["table_id"],
        "sheet_name": form["sheet_name"],
        "package_name": form["package_name"],

        "region": form.get("region", "-"),
        "departure_city": form.get("departure_city", "-"),
        "source": form.get("source", "-"),

        "amount_paid": form.get("amount_paid", "0"),
        "exchange_rate": form.get("exchange_rate", "495"),
        "discount": form.get("discount", "-"),
        "contract_number": form.get("contract_number", "-"),

        "visa_status": form.get("visa_status", "UMRAH VISA"),
        "avia": form.get("avia", "-"),
        "room_type": form.get("room_type", "-"),
        "meal_type": form.get("meal_type", "-"),
        "train": form.get("train", "-"),

        "price": form.get("price", "0"),
        "comment": form.get("comment", "-"),

        "manager_name_text": data.get("manager_name_text", "-"),
        "placement_type": form.get("placement_type", "separate"),
    }

    await finalize_booking_integrated(message, state, pilgrims, common, form)


from starlette.concurrency import run_in_threadpool
from bull_project.bull_bot.core.google_sheets.writer import save_group_booking
from bull_project.bull_bot.database.requests import add_booking_to_db, update_booking_row

async def finalize_booking_integrated(message: Message, state: FSMContext, pilgrims, common, form):
    status = await message.answer("⏳ <b>Записываю бронь...</b>", parse_mode="HTML")
    db_ids: list[int] = []

    try:
        # --- ДЕБАГ: Выводим данные паломников для проверки ---
        print(f"🔍 DEBUG: Всего паломников: {len(pilgrims)}")
        for i, p in enumerate(pilgrims):
            print(f"  Паломник {i+1}:")
            print(f"    Имя: {p.get('First Name', 'НЕТ')}")
            print(f"    Фамилия: {p.get('Last Name', 'НЕТ')}")
            print(f"    Пол: {p.get('Gender', 'НЕТ')}")
            print(f"    Дата рождения: {p.get('Date of Birth', 'НЕТ')}")
            print(f"    Номер паспорта: {p.get('Document Number', 'НЕТ')}")
            print(f"    Срок действия: {p.get('Document Expiration', 'НЕТ')}")
            print(f"    ИИН: {p.get('IIN', 'НЕТ')}")
            print(f"    Телефон: {p.get('client_phone', 'НЕТ')}")
            print(f"    Путь к фото: {p.get('passport_image_path', 'НЕТ')}")

        # --- 1. Запись КАЖДОГО паломника в БД ---
        for p in pilgrims:
            # Собираем ВСЕ данные паспорта
            last_name = p.get("Last Name") or p.get("guest_last_name") or "-"
            first_name = p.get("First Name") or p.get("guest_first_name") or "-"
            gender = p.get("Gender") or p.get("gender") or "-"
            dob = p.get("Date of Birth") or p.get("date_of_birth") or "-"
            passport_num = p.get("Document Number") or p.get("passport_num") or "-"
            passport_expiry = p.get("Document Expiration") or p.get("passport_expiry") or "-"
            iin = p.get("IIN") or "-"
            client_phone = p.get("client_phone") or "-"

            full_db_record = {
                "table_id": common["table_id"],
                "sheet_name": common["sheet_name"],
                "sheet_row_number": None,

                "package_name": common["package_name"],
                "region": common["region"],
                "departure_city": common["departure_city"],
                "source": common["source"],
                "amount_paid": common["amount_paid"],
                "exchange_rate": common["exchange_rate"],
                "discount": common["discount"],
                "contract_number": common["contract_number"],

                "visa_status": common["visa_status"],
                "avia": common["avia"],
                "avia_request": common["avia"],

                "room_type": common["room_type"],
                "meal_type": common["meal_type"],
                "train": common["train"],

                # --- ВАЖНО: Данные паспорта для БД ---
                "guest_last_name": last_name.upper() if last_name != "-" else "-",
                "guest_first_name": first_name.upper() if first_name != "-" else "-",
                "gender": gender.upper() if gender != "-" else "-",
                "date_of_birth": dob,
                "passport_num": passport_num.upper() if passport_num != "-" else "-",
                "passport_expiry": passport_expiry,
                "guest_iin": iin,

                "price": common["price"],
                "comment": common["comment"],
                "client_phone": client_phone,
                "manager_name_text": common["manager_name_text"],
                "placement_type": common["placement_type"],
                "passport_image_path": p.get("passport_image_path"),
                "status": "new",
            }

            # ДЕБАГ: Выводим запись для проверки
            print(f"📝 Запись в БД для {last_name} {first_name}:")
            print(f"   - passport_num: {full_db_record['passport_num']}")
            print(f"   - guest_iin: {full_db_record['guest_iin']}")
            print(f"   - date_of_birth: {full_db_record['date_of_birth']}")
            print(f"   - passport_image_path: {full_db_record['passport_image_path']}")

            booking_id = await add_booking_to_db(full_db_record, message.from_user.id)
            db_ids.append(booking_id)
            print(f"✅ ID записи в БД: {booking_id}")

        # --- 2. Подготовка данных для Google Sheets ---
        # Google Sheets ожидает данные в формате паспортного парсера
        sheets_pilgrims = []
        for p in pilgrims:
            sheets_pilgrim = {
                "Last Name": p.get("Last Name") or p.get("guest_last_name") or "-",
                "First Name": p.get("First Name") or p.get("guest_first_name") or "-",
                "Gender": p.get("Gender") or p.get("gender") or "M",
                "Date of Birth": p.get("Date of Birth") or p.get("date_of_birth") or "-",
                "Document Number": p.get("Document Number") or p.get("passport_num") or "-",
                "Document Expiration": p.get("Document Expiration") or p.get("passport_expiry") or "-",
                "IIN": p.get("IIN") or "-",
                "client_phone": p.get("client_phone") or "-",
                "passport_image_path": p.get("passport_image_path"),
            }
            sheets_pilgrims.append(sheets_pilgrim)

        # --- 3. Запись всех паломников в Google Sheets ---
        saved_rows = await save_group_booking(
            sheets_pilgrims,               # group_data с паспортными данными
            common,                        # common_data
            common['placement_type'],      # placement_mode
            form.get('specific_row'),      # specific_row
            form.get('is_share', False),   # is_share
        )

        await status.delete()

        if not saved_rows:
            user = await get_user_by_id(message.from_user.id)
            await message.answer(
                "⚠️ Не найдено мест в Google Sheets. Проверь пакет / тип номера / блок.",
                reply_markup=get_menu_by_role(user.role) if user else manager_kb(),
            )
            await state.clear()
            return

        # --- 4. Проставляем номера строк в БД ---
        for i, row in enumerate(saved_rows):
            if i < len(db_ids):
                await update_booking_row(db_ids[i], row)
                print(f"📌 Строка {row} для записи БД ID {db_ids[i]}")

        user = await get_user_by_id(message.from_user.id)
        await message.answer(
            f"✅ Бронь успешно записана!\n"
            f"• Записано паломников: {len(pilgrims)}\n"
            f"• Строки в таблице: {saved_rows}\n"
            f"• ID записей в БД: {db_ids}",
            reply_markup=get_menu_by_role(user.role) if user else manager_kb(),
        )
        await state.clear()

    except Exception as e:
        await status.delete()
        print(f"❌ Ошибка в finalize_booking_integrated: {e}")
        import traceback
        traceback.print_exc()
        user = await get_user_by_id(message.from_user.id)
        await message.answer(f"❌ Ошибка финализации брони: {e}", reply_markup=get_menu_by_role(user.role) if user else manager_kb())
# ==================== 4. ЗАПРОСЫ 4U ====================

@router.callback_query(F.data == "req_4u")
async def req_4u_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📅 <b>Напишите Даты:</b>\n(Например: 13.12-20.12)", parse_mode="HTML")
    await state.set_state(BookingFlow.waiting_4u_dates)

@router.message(BookingFlow.waiting_4u_dates)
async def req_4u_dates(message: Message, state: FSMContext):
    await state.update_data(r4_dates=message.text)
    await message.answer("👥 <b>Сколько человек?</b>")
    await state.set_state(BookingFlow.waiting_4u_count)

@router.message(BookingFlow.waiting_4u_count)
async def req_4u_count(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(r4_count=int(message.text))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Double", callback_data="r4_r:Double"), InlineKeyboardButton(text="Triple", callback_data="r4_r:Triple")],
        [InlineKeyboardButton(text="Quadro", callback_data="r4_r:Quadro"), InlineKeyboardButton(text="Single", callback_data="r4_r:Single")]
    ])
    await message.answer("🛏 <b>Тип размещения:</b>", reply_markup=kb)
    await state.set_state(BookingFlow.waiting_4u_room)

@router.callback_query(F.data.startswith("r4_r:"))
async def req_4u_finish(call: CallbackQuery, state: FSMContext):
    room = call.data.split(":")[1]
    data = await state.get_data()
    user = await get_user_by_id(call.from_user.id)
    req_id = await add_4u_request(call.from_user.id, user.full_name, data['r4_dates'], data['r4_count'], room, "MANUAL_4U")

    await call.message.edit_text(f"✅ <b>Запрос 4U #{req_id} отправлен!</b>", reply_markup=main_menu_kb())
    await state.clear()

@router.callback_query(F.data == "cancel")
async def cancel_handler(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user_by_id(call.from_user.id)
    await call.message.answer("❌ Отменено.", reply_markup=get_menu_by_role(user.role if user else "manager"))

@router.message(Command("test_webapp"))
async def test_webapp(message: Message):
    await message.answer("✅ Роутер работает!")

@router.message()
async def catch_all_messages(message: Message):
    print(f"📨 Получено сообщение любого типа:")
    print(f"  Тип: {type(message)}")
    print(f"  Контент: {message.text}")
    print(f"  Атрибуты: {dir(message)}")

    web_data = getattr(message, 'web_app_data', None)
    if web_data:
        print(f"  Есть web_app_data! {web_data.data}")

# ==================== 5. ОБРАБОТЧИКИ ВЫБОРА ТАБЛИЦЫ/ПАКЕТА ====================
# Добавляем обработчики для переноса брони

from bull_project.bull_bot.core.google_sheets.client import get_sheet_names, get_packages_from_sheet
from bull_project.bull_bot.config.keyboards import kb_select_sheet, kb_select_package

@router.callback_query(BookingFlow.choosing_table, F.data.startswith("sel_tab:"))
async def booking_sel_table(call: CallbackQuery, state: FSMContext):
    """Обработчик выбора таблицы при переносе"""
    sid = call.data.split(":")[1]

    # ДЕБАГ: Проверяем состояние ПЕРЕД обновлением
    data_before = await state.get_data()
    print(f"🔍 booking_sel_table - ПЕРЕД обновлением:")
    print(f"   pilgrims_list: {len(data_before.get('pilgrims_list', []))}")
    print(f"   is_reschedule: {data_before.get('is_reschedule', False)}")

    await state.update_data(current_sheet_id=sid)

    # ДЕБАГ: Проверяем состояние ПОСЛЕ обновления
    data_after = await state.get_data()
    print(f"🔍 booking_sel_table - ПОСЛЕ обновления:")
    print(f"   pilgrims_list: {len(data_after.get('pilgrims_list', []))}")

    sheets = get_sheet_names(sid)

    await call.message.edit_text(
        "✈️ <b>Выберите дату вылета:</b>",
        reply_markup=kb_select_sheet(sheets[:15], len(sheets) > 15),
        parse_mode="HTML"
    )
    await state.set_state(BookingFlow.choosing_date)
    await call.answer()

@router.callback_query(BookingFlow.choosing_date, F.data.startswith("sel_date:"))
async def booking_sel_date(call: CallbackQuery, state: FSMContext):
    """Обработчик выбора даты при переносе"""
    sname = call.data.split(":")[1]
    await state.update_data(current_sheet_name=sname)
    data = await state.get_data()

    pkgs = get_packages_from_sheet(data['current_sheet_id'], sname)
    await state.update_data(packages_map=pkgs)

    await call.message.edit_text(
        "📦 <b>Выберите пакет:</b>",
        reply_markup=kb_select_package(pkgs),
        parse_mode="HTML"
    )
    await state.set_state(BookingFlow.choosing_pkg)
    await call.answer()

@router.callback_query(BookingFlow.choosing_pkg, F.data.startswith("sel_pkg:"))
async def booking_sel_pkg(call: CallbackQuery, state: FSMContext):
    """Обработчик выбора пакета при переносе"""
    data = await state.get_data()
    row_id = int(call.data.split(":")[1])
    pkg_name = data['packages_map'].get(row_id, "Unknown")

    # ДЕБАГ: Проверяем состояние
    print(f"\n🔍 booking_sel_pkg - Состояние:")
    print(f"   is_reschedule: {data.get('is_reschedule', False)}")
    print(f"   pilgrims_list: {len(data.get('pilgrims_list', []))}")
    print(f"   reschedule_passport: {bool(data.get('reschedule_passport'))}")
    print(f"   old_booking_id: {data.get('old_booking_id', 'НЕТ')}")

    await state.update_data(selected_pkg_name=pkg_name)

    # ВАЖНО: Проверяем что это перенос
    is_reschedule = data.get('is_reschedule', False)

    if is_reschedule:
        # Для переноса - сразу отправляем в веб-форму
        await call.message.edit_text(
            f"✅ Выбрано:\n"
            f"📦 Пакет: {pkg_name}\n"
            f"📅 Дата: {data['current_sheet_name']}\n\n"
            f"Открываю форму для заполнения...",
            parse_mode="HTML"
        )
        await send_webapp_link(call.message, state)
    else:
        # Обычное бронирование - идем дальше
        await call.message.answer("Сколько паломников? (Число):", parse_mode="HTML")
        await state.set_state(BookingFlow.waiting_count)

    await call.answer()

# Добавьте в booking_handlers.py
@router.message(Command("test_form"))
async def test_form(message: Message):
    """Тестовая команда для запуска формы"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📝 ТЕСТОВАЯ ФОРМА",
            web_app=WebAppInfo(url=WEB_APP_URL)
        )]
    ])
    await message.answer("Нажмите для открытия формы:", reply_markup=kb)
