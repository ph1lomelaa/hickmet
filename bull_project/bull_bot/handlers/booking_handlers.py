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
from bull_project.bull_bot.core.parsers.passport_parser import PassportParser
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
    await message.answer("Отправьте паспорт 1-го паломника:")
    await state.set_state(BookingFlow.waiting_passport)

# В функции process_passport (строка ~100)

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
            pages = convert_from_path(temp_path, dpi=200, poppler_path=POPPLER_PATH)
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

    msg = await message.answer("⏳ Читаю данные...")

    try:
        parser = PassportParser(POPPLER_PATH)
        passport_result = parser.parse(path)  # Возвращает PassportData объект

        # 🔥 ИСПРАВЛЕНИЕ: Используем to_dict() для получения всех полей
        p_data = passport_result.to_dict()
        p_data['passport_image_path'] = path  # временно локальный путь

        # 🔥 КРИТИЧНО: Добавляем snake_case поля для writer.py
        p_data['last_name'] = p_data.get('Last Name', '-')
        p_data['first_name'] = p_data.get('First Name', '-')
        p_data['gender'] = p_data.get('Gender', 'M')
        p_data['dob'] = p_data.get('Date of Birth', '-')
        p_data['doc_num'] = p_data.get('Document Number', '-')
        p_data['doc_exp'] = p_data.get('Document Expiration', '-')
        p_data['iin'] = p_data.get('IIN', '-')

        # Логирование для проверки
        print(f"📋 PARSED DATA для паломника {curr}:")
        print(f"  Last Name: {p_data.get('Last Name')}")
        print(f"  First Name: {p_data.get('First Name')}")
        print(f"  Gender: {p_data.get('Gender')}")
        print(f"  DOB: {p_data.get('Date of Birth')}")
        print(f"  Document Number: {p_data.get('Document Number')}")
        print(f"  IIN: {p_data.get('IIN')}")

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

        if not p_data.get('Last Name'):
            await state.update_data(temp_p=p_data)
            await message.answer("⚠️ Не распознано. Введите <b>Фамилию и Имя</b> вручную:", parse_mode="HTML")
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
        await message.answer(f"✅ Ок. Паспорт <b>{data['current_pilgrim']+1}-го</b>:")
        await state.set_state(BookingFlow.waiting_passport)
    else:
        await send_webapp_link(message, state)

# В функции send_webapp_link (строка ~145)

async def send_webapp_link(message: Message, state: FSMContext):
    data = await state.get_data()
    pilgrims = data['pilgrims_list']

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
