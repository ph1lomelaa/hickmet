import os
from datetime import datetime
import uvicorn
from urllib.parse import unquote_plus
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel

# Импорты вашего проекта
from bull_project.bull_bot.core.smart_search import get_packages_by_date
from bull_project.bull_bot.core.google_sheets.allocator import get_open_rooms_for_manual_selection
from bull_project.bull_bot.core.google_sheets.client import (
    get_google_client,
    get_sheet_data,
    get_accessible_tables,
    get_sheet_names,
)
from bull_project.bull_bot.core.google_sheets.writer import save_group_booking
from bull_project.bull_bot.database.setup import init_db
from bull_project.bull_bot.database.requests import (
    add_booking_to_db,
    update_booking_row,
    add_user,
)
from bull_project.bull_bot.core.parsers.passport_parser import PassportParser
from bull_project.bull_bot.database.requests import (
    get_last_n_bookings_by_manager,
    get_booking_by_id,
    mark_booking_cancelled,
    get_full_analytics,
    get_manager_detailed_stats,
    search_packages_by_date,
    get_all_managers_list,
    get_all_bookings_for_period,
    search_tourist_by_name,
    get_db_packages_list,
    get_all_bookings_in_package
)
from bull_project.bull_bot.database.requests import get_latest_passport_for_person
from bull_project.bull_bot.core.google_sheets.writer import (
    clear_booking_in_sheets,
    write_cancelled_booking_red
)
from bull_project.bull_bot.config.constants import ABS_UPLOADS_DIR
# uploads dir is shared via volume on API service
os.makedirs(ABS_UPLOADS_DIR, exist_ok=True)
# Инициализация парсера паспортов
passport_parser = PassportParser(debug=False)

# -----------------------------------------------------------------------------
# FASTAPI НАСТРОЙКА
# -----------------------------------------------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CARE_WEBAPP_DIR = os.path.join(PROJECT_ROOT, "care_webapp")
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")

# Инициализация БД при старте приложения
@app.on_event("startup")
async def startup_event():
    await init_db()

if os.path.isdir(CARE_WEBAPP_DIR):
    app.mount(
        "/care-webapp",
        StaticFiles(directory=CARE_WEBAPP_DIR, html=True),
        name="care-webapp",
    )
if os.path.isdir(ASSETS_DIR):
    app.mount(
        "/assets",
        StaticFiles(directory=ASSETS_DIR, html=False),
        name="assets",
    )

@app.get("/health")
async def health():
    return {"ok": True}

# -----------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------------------------------------------------------
def normalize_sheet_and_package(raw_sheet_name: str, raw_package_name: str):
    """Очищает названия от лишних символов перед записью."""
    s_name = unquote_plus(raw_sheet_name).strip()
    p_name = unquote_plus(raw_package_name).strip()
    if "[" in p_name and "]" in p_name:
        p_name = p_name.split("[")[0].strip()
    return s_name, p_name


def get_active_tables_for_care() -> Dict[str, str]:
    """
    Возвращает словарь таблиц за текущий и следующий год.
    Если фильтр ничего не вернул, отдаём все доступные таблицы.
    """
    tables = get_accessible_tables() or {}
    now = datetime.now()
    years = {str(now.year), str(now.year + 1)}
    filtered = {name: table_id for name, table_id in tables.items() if any(y in name for y in years)}
    return filtered or tables

async def resolve_passport_path(booking) -> Optional[str]:
    """
    Возвращает путь к паспорту для брони, с фолбэком на последнее фото по ФИО.
    """
    passport_path = booking.passport_image_path
    if not passport_path and booking.guest_last_name and booking.guest_first_name:
        passport_path = await get_latest_passport_for_person(
            booking.guest_last_name,
            booking.guest_first_name
        )
    return passport_path

# -----------------------------------------------------------------------------
# МОДЕЛИ ДАННЫХ (Pydantic)
# -----------------------------------------------------------------------------

class PilgrimData(BaseModel):
    first_name: str = "-"
    last_name: str = "-"
    phone: str = "-"
    passport_num: str = "-"
    date_of_birth: str = "-"
    gender: str = "M"
    passport_expiry: str = "-"
    iin: str = "-"
    passport_image_path: str = None

class BookingSubmitIn(BaseModel):
    pilgrims: List[PilgrimData] = []

    package_name: str
    sheet_name: str
    table_id: str

    departure_city: str = "-"
    room_type: str = "-"
    meal_type: str = "-"
    visa_status: str = "UMRAH VISA"
    avia: str = "-"
    price: str = "0"
    amount_paid: str = "0"
    contract_number: str = "-"
    exchange_rate: str = "495"
    discount: str = "-"
    source: str = "-"
    region: str = "-"
    train: str = "-"
    manager_name_text: str = "-"
    comment: str = "-"

    placement_type: str = "separate"
    specific_row: Optional[int] = None
    manager_id: Optional[int] = None

# -----------------------------------------------------------------------------
# API ENDPOINTS
# -----------------------------------------------------------------------------

@app.get("/api/packages")
async def api_packages(date: str):
    """Поиск пакетов по дате (Smart Search)."""
    try:
        print(f"🔍 Запрос пакетов для даты: '{date}'")

        # Правильный вызов асинхронной функции
        results = await get_packages_by_date(date_part=date, force=False)

        print(f"✅ Результат поиска: found={results.get('found')}, data_count={len(results.get('data', []))}")

        return {
            "ok": True,
            "found": results.get("found", False),
            "data": results.get("data", [])
        }
    except Exception as e:
        print(f"❌ Ошибка в /api/packages: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": str(e),
                "found": False,
                "data": []
            }
        )

@app.get("/api/rooms")
async def api_rooms(
        table_id: str,
        sheet_name: str,
        package_name: str,
        count: int = 1,
        room_type: str = "Quad",
        gender: str = "M",
):
    """Получение списка свободных комнат."""
    s_name, p_name = normalize_sheet_and_package(sheet_name, package_name)
    try:
        # Получаем данные таблицы
        all_rows = await run_in_threadpool(get_sheet_data, table_id, s_name)

        rooms = await run_in_threadpool(
            get_open_rooms_for_manual_selection,
            all_rows, p_name, count, room_type, gender
        )
        return {"ok": True, "found": len(rooms) > 0, "rooms": rooms}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.post("/api/passport/parse")
async def api_passport_parse(file: UploadFile = File(...)):
    """Парсинг паспорта и извлечение данных + сохранение файла"""
    try:
        import time
        from pdf2image import convert_from_path
        from PIL import Image

        # Создаем директорию для uploads если её нет
        uploads_dir = os.path.join(PROJECT_ROOT, "tmp", "uploads")
        os.makedirs(uploads_dir, exist_ok=True)

        # Генерируем уникальное имя файла
        timestamp = int(time.time() * 1000)
        ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
        temp_path = f"/tmp/passport_{timestamp}_temp{ext}"

        # Сохраняем временный файл
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        print(f"📥 Веб-форма: файл загружен {temp_path}")

        # Конвертируем в PNG
        png_path = os.path.join(uploads_dir, f"web_{timestamp}.png")

        try:
            if temp_path.lower().endswith('.pdf'):
                # Конвертируем PDF в PNG
                print(f"🔄 Конвертация PDF в PNG...")
                poppler_path = os.getenv("POPPLER_PATH", "/opt/homebrew/bin")
                pages = convert_from_path(temp_path, dpi=200, poppler_path=poppler_path)
                if pages:
                    pages[0].save(png_path, 'PNG')
                    print(f"✅ PDF сконвертирован: {png_path}")
            else:
                # Конвертируем изображение в PNG
                img = Image.open(temp_path)
                img.save(png_path, 'PNG')
                print(f"✅ Изображение сохранено: {png_path}")
        except Exception as conv_err:
            print(f"⚠️ Ошибка конвертации: {conv_err}, используем оригинал")
            png_path = temp_path

        # Парсим паспорт
        passport_data = await run_in_threadpool(passport_parser.parse, temp_path)

        # Удаляем временный файл (если это не финальный файл)
        if temp_path != png_path and os.path.exists(temp_path):
            os.remove(temp_path)

        if not passport_data.is_valid:
            # Удаляем сохраненный файл если данные невалидны
            if os.path.exists(png_path):
                os.remove(png_path)
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Не удалось распознать данные паспорта"}
            )

        result_data = passport_data.to_dict()
        result_data['passport_image_path'] = png_path

        print(f"✅ Веб-форма: паспорт сохранен в {png_path}")

        return {
            "ok": True,
            "data": result_data
        }

    except Exception as e:
        print(f"❌ Ошибка парсинга паспорта через веб-форму: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": f"Ошибка обработки файла: {str(e)}"}
        )


@app.post("/api/bookings/submit")
async def api_bookings_submit(payload: BookingSubmitIn):
    """
    Создание бронирования.
    """

    # 🔥 ДОБАВЛЕНО: Логирование входящих данных
    print("\n" + "="*60)
    print("📥 ПОЛУЧЕН ЗАПРОС /api/bookings/submit")
    print("="*60)
    print(f"Количество паломников: {len(payload.pilgrims)}")

    for i, p in enumerate(payload.pilgrims):
        print(f"\n👤 Паломник {i+1}:")
        print(f"  Фамилия: {p.last_name}")
        print(f"  Имя: {p.first_name}")
        print(f"  Пол: {p.gender}")
        print(f"  Дата рождения: {p.date_of_birth}")
        print(f"  Номер паспорта: {p.passport_num}")
        print(f"  Срок действия: {p.passport_expiry}")
        print(f"  ИИН: {p.iin}")
        print(f"  Телефон: {p.phone}")

    print("\n📦 Общие данные:")
    print(f"  Пакет: {payload.package_name}")
    print(f"  Лист: {payload.sheet_name}")
    print(f"  Таблица: {payload.table_id}")
    print(f"  Тип комнаты: {payload.room_type}")
    print("="*60 + "\n")

    # 0. Защита от пустого списка
    if not payload.pilgrims:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "Список паломников пуст"}
        )

    # 1. Проверяем/создаем менеджера в БД
    manager_id = payload.manager_id or 0
    try:
        await add_user(
            manager_id,
            payload.manager_name_text or "Manager",
            username="-",
            role="manager",
            )
    except Exception:
        pass  # если уже есть — игнорируем

    # 2. Нормализация имен
    sheet_name, package_name = normalize_sheet_and_package(
        payload.sheet_name,
        payload.package_name,
    )

    # 3. Подготовка общих данных (Common Data)
    visa_status_value = (payload.visa_status or "UMRAH VISA").strip()
    if visa_status_value.upper() == "NO VISA":
        visa_status_value = "-"

    common = {
        "table_id": payload.table_id,
        "sheet_name": sheet_name,
        "package_name": package_name,
        "region": payload.region or "-",
        "departure_city": payload.departure_city or "-",
        "source": payload.source or "-",
        "amount_paid": str(payload.amount_paid or "0"),
        "exchange_rate": str(payload.exchange_rate or "495"),
        "discount": payload.discount or "-",
        "contract_number": payload.contract_number or "-",
        "visa_status": visa_status_value,
        "avia": payload.avia or "-",
        "avia_request": payload.avia or "-",
        "room_type": payload.room_type or "-",
        "meal_type": payload.meal_type or "-",
        "train": payload.train or "-",
        "price": str(payload.price or "0"),
        "comment": payload.comment or "-",
        "manager_name_text": payload.manager_name_text or "-",
        "placement_type": payload.placement_type or "separate",
    }

    # 4. Формирование данных для Google Sheets и БД
    group_data_for_sheets: List[Dict[str, Any]] = []
    db_ids: List[int] = []

    for pilgrim in payload.pilgrims:
        # Данные для Sheets
        p_sheet_data = {
            # Human Readable формат
            "Last Name": pilgrim.last_name or "-",
            "First Name": pilgrim.first_name or "-",
            "Gender": pilgrim.gender or "M",
            "Date of Birth": pilgrim.date_of_birth or "-",
            "Document Number": pilgrim.passport_num or "-",
            "Document Expiration": pilgrim.passport_expiry or "-",
            "IIN": pilgrim.iin or "-",
            "client_phone": pilgrim.phone or "-",
            "phone": pilgrim.phone or "-"
        }
        group_data_for_sheets.append(p_sheet_data)

        # Логирование данных для Sheets
        print(f"📄 Отправка в Sheets для {pilgrim.last_name}:")
        print(f"   Last Name: {p_sheet_data['Last Name']}")
        print(f"   First Name: {p_sheet_data['First Name']}")
        print(f"   Gender: {p_sheet_data['Gender']}")
        print(f"   DOB: {p_sheet_data['Date of Birth']}")
        print(f"   Doc Number: {p_sheet_data['Document Number']}")
        print(f"   IIN: {p_sheet_data['IIN']}")

        # Данные для БД
        record_db = {
            "table_id": payload.table_id,
            "sheet_name": sheet_name,
            "sheet_row_number": None,
            "package_name": package_name,
            "region": common["region"],
            "departure_city": common["departure_city"],
            "source": common["source"],
            "amount_paid": common["amount_paid"],
            "exchange_rate": common["exchange_rate"],
            "discount": common["discount"],
            "contract_number": common["contract_number"],
            "visa_status": common["visa_status"],
            "avia": common["avia"],
            "avia_request": common["avia_request"],
            "room_type": common["room_type"],
            "meal_type": common["meal_type"],
            "train": common["train"],
            "price": common["price"],
            "comment": common["comment"],
            "manager_name_text": common["manager_name_text"],
            "placement_type": common["placement_type"],
            "guest_last_name": pilgrim.last_name or "-",
            "guest_first_name": pilgrim.first_name or "-",
            "gender": pilgrim.gender or "M",
            "date_of_birth": pilgrim.date_of_birth or "-",
            "passport_num": pilgrim.passport_num or "-",
            "passport_expiry": pilgrim.passport_expiry or "-",
            "guest_iin": pilgrim.iin or "-",
            "client_phone": pilgrim.phone or "-",
            "passport_image_path": pilgrim.passport_image_path or None,
            "status": "new",
        }

        # Логирование данных для БД
        print(f"\n💾 Сохранение в БД для {pilgrim.last_name}:")
        print(f"   guest_last_name: {record_db['guest_last_name']}")
        print(f"   guest_first_name: {record_db['guest_first_name']}")
        print(f"   gender: {record_db['gender']}")
        print(f"   date_of_birth: {record_db['date_of_birth']}")
        print(f"   passport_num: {record_db['passport_num']}")
        print(f"   guest_iin: {record_db['guest_iin']}")

        # Сохраняем в БД
        booking_id = await add_booking_to_db(record_db, manager_id)
        db_ids.append(booking_id)
        print(f"✅ ID записи в БД: {booking_id}\n")

    # 5. Запись в Google Sheets
    saved_rows = []
    try:
        saved_rows = await save_group_booking(
            group_data=group_data_for_sheets,
            common_data=common,
            placement_mode=common["placement_type"],
            specific_row=payload.specific_row,
            is_share=False,
        )

        print(f"\n✅ Записано в Google Sheets, строки: {saved_rows}")

    except Exception as e:
        print(f"❌ Ошибка записи в Sheets: {e}")
        import traceback
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": f"Записано в БД, но ошибка Sheets: {e}",
                "db_ids": db_ids,
                "saved_rows": [],
            },
        )

    if not saved_rows:
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "error": "Место не найдено (Sheets). Попробуйте другой тип номера.",
                "db_ids": db_ids,
                "saved_rows": [],
            },
        )

    # 6. Обновляем row_number в БД
    for i, row in enumerate(saved_rows):
        if i < len(db_ids):
            await update_booking_row(db_ids[i], row)
            print(f"📌 Строка {row} для записи БД ID {db_ids[i]}")

    print("\n" + "="*60)
    print("✅ ЗАПРОС УСПЕШНО ОБРАБОТАН")
    print(f"   Записано паломников: {len(payload.pilgrims)}")  # 🔥 ИСПРАВЛЕНО
    print(f"   Строки в таблице: {saved_rows}")
    print(f"   ID записей в БД: {db_ids}")
    print("="*60 + "\n")

    return {"ok": True, "db_ids": db_ids, "saved_rows": saved_rows}


@app.get("/api/history/{manager_id}")
async def get_manager_history(manager_id: int):
    """
    Получение истории бронирований менеджера
    """
    try:
        print(f"\n📋 Запрос истории для менеджера {manager_id}")
        
        # Получаем последние 100 бронирований менеджера
        bookings = await get_last_n_bookings_by_manager(manager_id, limit=100, include_cancelled=True)
        
        if not bookings:
            return {
                "ok": True,
                "bookings": [],
                "message": "История пуста"
            }
        
        
        bookings_data = []
        for b in bookings:
            passport_path = await resolve_passport_path(b)
            bookings_data.append( {
                "id": b.id,
                "manager_id": b.manager_id,
                "table_id": b.table_id,
                "sheet_name": b.sheet_name,
                "sheet_row_number": b.sheet_row_number,
                "package_name": b.package_name,
                "region": b.region,
                "departure_city": b.departure_city,
                "source": b.source,
                "amount_paid": b.amount_paid,
                "exchange_rate": b.exchange_rate,
                "discount": b.discount,
                "contract_number": b.contract_number,
                "visa_status": b.visa_status,
                "avia": b.avia,
                "avia_request": b.avia_request,
                "room_type": b.room_type,
                "meal_type": b.meal_type,
                "train": b.train,
                "price": b.price,
                "comment": b.comment,
                "manager_name_text": b.manager_name_text,
                "placement_type": b.placement_type,
                "guest_last_name": b.guest_last_name,
                "guest_first_name": b.guest_first_name,
                "gender": b.gender,
                "date_of_birth": b.date_of_birth,
                "passport_num": b.passport_num,
                "passport_expiry": b.passport_expiry,
                "guest_iin": b.guest_iin,
                "client_phone": b.client_phone,
                "passport_image_path": passport_path,
                "status": b.status,
                "created_at": b.created_at.isoformat() if b.created_at else None
            })
        
        print(f"✅ Найдено {len(bookings_data)} бронирований")
        
        return {
            "ok": True,
            "bookings": bookings_data
        }
        
    except Exception as e:
        print(f"❌ Ошибка получения истории: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )

@app.post("/api/passports/upload")
async def api_passport_upload(file: UploadFile = File(...)):
    """
    Принимает файл паспорта от бота и сохраняет на стороне API (общий volume).
    Возвращает путь к сохраненному файлу.
    """
    try:
        # Генерируем уникальное имя
        ts = int(datetime.now().timestamp() * 1000)
        orig_ext = os.path.splitext(file.filename or "")[1] or ".png"
        safe_ext = orig_ext if len(orig_ext) <= 5 else ".png"
        target_path = os.path.join(ABS_UPLOADS_DIR, f"bot_upload_{ts}{safe_ext}")

        # Сохраняем файл
        with open(target_path, "wb") as f:
            content = await file.read()
            f.write(content)

        return {"ok": True, "path": target_path}
    except Exception as e:
        print(f"❌ Ошибка загрузки паспорта от бота: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


@app.post("/api/bookings/{booking_id}/cancel")
async def cancel_booking_endpoint(booking_id: int):
    """
    Отмена бронирования с записью красным цветом
    """
    try:
        print(f"\n❌ Запрос на отмену брони #{booking_id}")
        
        # Получаем данные брони
        booking = await get_booking_by_id(booking_id)
        if not booking:
            return JSONResponse(
                status_code=404,
                content={"ok": False, "error": "Бронь не найдена"}
            )
        
        # 1. Очищаем данные из Google Sheets
        sheets_cleared = False
        if booking.sheet_row_number and booking.table_id and booking.sheet_name:
            print(f"📝 Очистка данных из строки {booking.sheet_row_number}")
            sheets_cleared = await clear_booking_in_sheets(
                booking.table_id,
                booking.sheet_name,
                booking.sheet_row_number,
                booking.package_name
            )
        
        # 2. Записываем отмену красным цветом
        red_written = False
        if booking.table_id and booking.sheet_name and booking.package_name:
            guest_name = f"{booking.guest_last_name} {booking.guest_first_name}"
            print(f"🔴 Запись отмены красным для: {guest_name}")
            red_written = await write_cancelled_booking_red(
                booking.table_id,
                booking.sheet_name,
                booking.package_name,
                guest_name
            )
        
        # 3. Помечаем в БД как отмененную
        await mark_booking_cancelled(booking_id)
        print(f"💾 Статус в БД обновлен на 'cancelled'")
        
        return {
            "ok": True,
            "sheets_cleared": sheets_cleared,
            "red_written": red_written,
            "message": "Бронь успешно отменена"
        }
        
    except Exception as e:
        print(f"❌ Ошибка отмены брони: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


@app.get("/api/bookings/{booking_id}")
async def get_booking_details(booking_id: int):
    """
    Получение детальной информации о бронировании
    """
    try:
        booking = await get_booking_by_id(booking_id)
        if not booking:
            return JSONResponse(
                status_code=404,
                content={"ok": False, "error": "Бронь не найдена"}
            )
        
        return {
            "ok": True,
            "booking": {
                "id": booking.id,
                "guest_last_name": booking.guest_last_name,
                "guest_first_name": booking.guest_first_name,
                "gender": booking.gender,
                "date_of_birth": booking.date_of_birth,
                "passport_num": booking.passport_num,
                "passport_expiry": booking.passport_expiry,
                "guest_iin": booking.guest_iin,
                "client_phone": booking.client_phone,
                "package_name": booking.package_name,
                "sheet_name": booking.sheet_name,
                "sheet_row_number": booking.sheet_row_number,
                "room_type": booking.room_type,
                "meal_type": booking.meal_type,
                "price": booking.price,
                "amount_paid": booking.amount_paid,
                "visa_status": booking.visa_status,
                "status": booking.status
            }
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


# === НОВЫЕ ENDPOINTS ДЛЯ АДМИН WEBAPP ===

@app.get("/api/admin/analytics")
async def get_admin_analytics(
    start_date: str = Query(..., description="Дата начала (YYYY-MM-DD)"),
    end_date: str = Query(..., description="Дата конца (YYYY-MM-DD)")
):
    """
    Получение полной аналитики за период для админ панели
    """
    try:
        from datetime import datetime

        # Парсим даты
        d1 = datetime.strptime(start_date, "%Y-%m-%d").date()
        d2 = datetime.strptime(end_date, "%Y-%m-%d").date()

        print(f"\n📊 Запрос аналитики за период: {d1} - {d2}")

        # Получаем полную статистику
        stats = await get_full_analytics(d1, d2)

        print(f"✅ Статистика получена: {stats['total_bookings']} броней")

        return {
            "ok": True,
            **stats
        }

    except Exception as e:
        print(f"❌ Ошибка получения аналитики: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


@app.get("/api/admin/managers")
async def get_all_managers():
    """
    Получение списка всех менеджеров
    """
    try:
        managers = await get_all_managers_list()

        managers_data = []
        for m in managers:
            managers_data.append({
                "telegram_id": m.telegram_id,
                "full_name": m.full_name,
                "username": m.username,
                "role": m.role
            })

        return {
            "ok": True,
            "managers": managers_data
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


@app.get("/api/admin/manager/{manager_id}")
async def get_manager_stats(
    manager_id: int,
    start_date: str = Query(...),
    end_date: str = Query(...)
):
    """
    Детальная статистика по конкретному менеджеру
    """
    try:
        from datetime import datetime

        # Формат даты должен быть YYYY-MM-DD (без пробелов)
        d1 = datetime.strptime(start_date, "%Y-%m-%d").date()
        d2 = datetime.strptime(end_date, "%Y-%m-%d").date()

        stats = await get_manager_detailed_stats(manager_id, d1, d2)

        # Преобразуем брони в JSON формат
        bookings_data = []
        for b in stats['bookings']:
            passport_path = await resolve_passport_path(b)
            bookings_data.append({
                "id": b.id,
                "guest_last_name": b.guest_last_name,
                "guest_first_name": b.guest_first_name,
                "package_name": b.package_name,
                "sheet_name": b.sheet_name,
                "price": b.price,
                "status": b.status,
                "passport_image_path": passport_path,
                "created_at": b.created_at.isoformat() if b.created_at else None
            })

        return {
            "ok": True,
            "total": stats['total'],
            "active": stats['active'],
            "cancelled": stats['cancelled'],
            "top_packages": stats['top_packages'],
            "bookings": bookings_data
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


@app.get("/api/admin/search/packages")
async def search_packages_endpoint(date: str = Query(..., description="Дата для поиска (ДД.ММ)")):
    """
    Поиск пакетов по дате
    """
    try:
        results = await search_packages_by_date(date)

        packages_data = []
        for sheet, pkg, cnt in results:
            packages_data.append({
                "sheet_name": sheet,
                "package_name": pkg,
                "count": cnt
            })

        return {
            "ok": True,
            "packages": packages_data
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


@app.get("/api/admin/bookings")
async def get_all_bookings(
    start_date: str = Query(..., description="Дата начала (YYYY-MM-DD)"),
    end_date: str = Query(..., description="Дата конца (YYYY-MM-DD)")
):
    """
    Получение списка всех броней за период
    """
    try:
        from datetime import datetime

        d1 = datetime.strptime(start_date, "%Y-%m-%d").date()
        d2 = datetime.strptime(end_date, "%Y-%m-%d").date()

        bookings = await get_all_bookings_for_period(d1, d2)

        bookings_data = []
        for b in bookings:
            passport_path = await resolve_passport_path(b)
            bookings_data.append({
                "id": b.id,
                "table_id": b.table_id,
                "guest_last_name": b.guest_last_name,
                "guest_first_name": b.guest_first_name,
                "gender": b.gender,
                "date_of_birth": b.date_of_birth,
                "guest_iin": b.guest_iin,
                "passport_num": b.passport_num,
                "passport_expiry": b.passport_expiry,
                "passport_image_path": passport_path,
                "client_phone": b.client_phone,
                "package_name": b.package_name,
                "sheet_name": b.sheet_name,
                "sheet_row_number": b.sheet_row_number,
                "room_type": b.room_type,
                "placement_type": b.placement_type,
                "meal_type": b.meal_type,
                "visa_status": b.visa_status,
                "avia": b.avia,
                "train": b.train,
                "departure_city": b.departure_city,
                "region": b.region,
                "source": b.source,
                "price": b.price,
                "amount_paid": b.amount_paid,
                "status": b.status,
                "manager_name": b.manager_name_text or b.manager_name,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "comment": b.comment or ""
            })

        return {
            "ok": True,
            "bookings": bookings_data
        }

    except Exception as e:
        print(f"❌ Ошибка получения броней: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


# -----------------------------------------------------------------------------
# CARE DEPARTMENT ENDPOINTS (Отдел Заботы)
# -----------------------------------------------------------------------------

@app.get("/api/care/tables")
async def get_care_tables():
    """Возвращает список таблиц (Google Sheets) для отдела заботы."""
    try:
        tables = get_active_tables_for_care()
        if not tables:
            return {"ok": False, "error": "Нет доступных таблиц"}

        return {"ok": True, "tables": tables}
    except Exception as e:
        print(f"❌ Ошибка получения таблиц отдела заботы: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


@app.get("/api/care/sheets")
async def get_care_sheets(table_id: str = Query(...)):
    """Возвращает список листов в выбранной таблице."""
    try:
        sheets = get_sheet_names(table_id) or []
        return {"ok": True, "sheets": sheets}
    except Exception as e:
        print(f"❌ Ошибка получения листов: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


@app.get("/api/care/search")
async def care_search_tourist(query: str = Query(..., min_length=1)):
    """
    Поиск паломника по имени/фамилии (без учета регистра, пробелов).
    Возвращает список найденных паломников с фото паспорта и всей информацией.
    """
    try:
        # Нормализуем запрос: убираем лишние пробелы
        query_normalized = " ".join(query.strip().split())

        print(f"🔍 Care Search: ищем '{query_normalized}'")

        # Поиск в БД
        results = await search_tourist_by_name(query_normalized)

        if not results:
            return {
                "ok": True,
                "results": []
            }

        # Формируем ответ
        tourists_data = []
        for booking in results:
            has_passport = bool(booking.passport_image_path)

            # Если паспорта нет, пробуем взять самый свежий по этому же ФИО
            fallback_passport = None
            if not has_passport and booking.guest_last_name and booking.guest_first_name:
                try:
                    fallback_passport = await get_latest_passport_for_person(
                        booking.guest_last_name,
                        booking.guest_first_name
                    )
                    if fallback_passport and not os.path.exists(fallback_passport):
                        fallback_passport = None
                except Exception:
                    fallback_passport = None

            tourists_data.append({
                "id": booking.id,
                "last_name": booking.guest_last_name or "-",
                "first_name": booking.guest_first_name or "-",
                "gender": booking.gender or "-",
                "date_of_birth": booking.date_of_birth or "-",
                "passport_num": booking.passport_num or "-",
                "passport_expiry": booking.passport_expiry or "-",
                "iin": booking.guest_iin or "-",
                "phone": booking.client_phone or "-",
                "package_name": booking.package_name or "-",
                "sheet_name": booking.sheet_name or "-",
                "room_type": booking.room_type or "-",
                "meal_type": booking.meal_type or "-",
                "price": booking.price or "-",
                "amount_paid": booking.amount_paid or "-",
                "manager_name": booking.manager_name_text or "-",
                "comment": booking.comment or "",
                "visa_status": booking.visa_status or "-",
                "avia": booking.avia or "-",
                "train": booking.train or "-",
                "region": booking.region or "-",
                "departure_city": booking.departure_city or "-",
                "source": booking.source or "-",
                "passport_image_path": booking.passport_image_path or fallback_passport or None,
                "created_at": booking.created_at.isoformat() if booking.created_at else None,
                "status": booking.status
            })
            print(
                f"  Паломник {booking.guest_last_name} {booking.guest_first_name}: "
                f"паспорт={has_passport}, путь={booking.passport_image_path or fallback_passport}"
            )

        print(f"✅ Найдено {len(tourists_data)} результатов")

        return {
            "ok": True,
            "results": tourists_data
        }

    except Exception as e:
        print(f"❌ Ошибка поиска: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


@app.get("/api/care/passport-photo/{booking_id}")
async def get_passport_photo(booking_id: int):
    """
    Возвращает фото паспорта для конкретной брони.
    """
    try:
        booking = await get_booking_by_id(booking_id)

        if not booking:
            return JSONResponse(
                status_code=404,
                content={"ok": False, "error": "Booking not found"}
            )

        # Ищем актуальный путь: сначала в самой брони, иначе берём самое свежее фото по ФИО
        passport_path = booking.passport_image_path
        if not passport_path and booking.guest_last_name and booking.guest_first_name:
            passport_path = await get_latest_passport_for_person(
                booking.guest_last_name,
                booking.guest_first_name
            )

        if not passport_path:
            return JSONResponse(
                status_code=404,
                content={"ok": False, "error": "No passport image for this booking"}
            )

        # Проверяем существование файла
        if not os.path.exists(passport_path):
            return JSONResponse(
                status_code=404,
                content={"ok": False, "error": f"Passport image file not found: {passport_path}"}
            )

        # Определяем тип файла по расширению
        file_ext = os.path.splitext(passport_path)[1].lower()
        media_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.pdf': 'application/pdf'
        }
        media_type = media_types.get(file_ext, 'image/png')  # По умолчанию PNG

        # Отдаем файл
        return FileResponse(
            passport_path,
            media_type=media_type,
            filename=f"passport_{booking_id}{file_ext}"
        )

    except Exception as e:
        print(f"❌ Ошибка получения фото паспорта: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


@app.get("/api/care/packages-by-date")
async def get_packages_by_date_for_care(
    table_id: str = Query(...),
    sheet_name: str = Query(...)
):
    """
    Возвращает список пакетов на конкретной дате (для выбора date sheet).
    """
    try:
        print(f"📋 Care Packages: table_id={table_id}, sheet_name={sheet_name}")

        packages = await get_db_packages_list(table_id, sheet_name)

        return {
            "ok": True,
            "packages": list(packages)
        }

    except Exception as e:
        print(f"❌ Ошибка получения пакетов: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


@app.get("/api/care/bookings-in-package")
async def get_bookings_in_package_for_care(
    table_id: str = Query(...),
    sheet_name: str = Query(...),
    package_name: str = Query(...)
):
    """
    Возвращает все брони в конкретном пакете со всей информацией.
    """
    try:
        print(f"📋 Care Bookings: package='{package_name}', sheet='{sheet_name}'")

        bookings = await get_all_bookings_in_package(table_id, sheet_name, package_name)

        bookings_data = []
        for b in bookings:
            passport_path = await resolve_passport_path(b)
            bookings_data.append({
                "id": b.id,
                "last_name": b.guest_last_name or "-",
                "first_name": b.guest_first_name or "-",
                "package_name": b.package_name or "-",
                "sheet_name": b.sheet_name or "-",
                "table_id": b.table_id or "-",
                "gender": b.gender or "-",
                "date_of_birth": b.date_of_birth or "-",
                "passport_num": b.passport_num or "-",
                "passport_expiry": b.passport_expiry or "-",
                "iin": b.guest_iin or "-",
                "phone": b.client_phone or "-",
                "room_type": b.room_type or "-",
                "meal_type": b.meal_type or "-",
                "price": b.price or "-",
                "amount_paid": b.amount_paid or "-",
                "manager_name": b.manager_name_text or "-",
                "comment": b.comment or "",
                "visa_status": b.visa_status or "-",
                "avia": b.avia or "-",
                "train": b.train or "-",
                "region": b.region or "-",
                "departure_city": b.departure_city or "-",
                "source": b.source or "-",
                "passport_image_path": passport_path or None,
                "sheet_row_number": b.sheet_row_number,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "status": b.status
            })

        print(f"✅ Найдено {len(bookings_data)} броней в пакете")

        return {
            "ok": True,
            "bookings": bookings_data
        }

    except Exception as e:
        print(f"❌ Ошибка получения броней: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


@app.get("/api/care/phones-by-package")
async def get_phones_by_package(
    table_id: str = Query(...),
    sheet_name: str = Query(...),
    package_name: str = Query(...)
):
    """
    Возвращает список телефонов с именами для конкретного пакета.
    """
    try:
        print(f"📞 Care Phones: package='{package_name}'")

        bookings = await get_all_bookings_in_package(table_id, sheet_name, package_name)

        phones_data = []
        for b in bookings:
            if b.client_phone and b.client_phone != "-":
                phones_data.append({
                    "name": f"{b.guest_last_name or ''} {b.guest_first_name or ''}".strip(),
                    "phone": b.client_phone
                })

        print(f"✅ Найдено {len(phones_data)} телефонов")

        return {
            "ok": True,
            "phones": phones_data
        }

    except Exception as e:
        print(f"❌ Ошибка получения телефонов: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )

# ============= ДОБАВЬ ЭТО =============

# Корневой маршрут для WebApp
@app.get("/")
async def root():
    """Главная страница"""
    index_path = os.path.join(CARE_WEBAPP_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Bull API", "status": "running"}


# Раздача всех статических файлов
@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    """Fallback для всех файлов"""
    
    # Игнорируем API роуты
    if full_path.startswith("api/"):
        return {"error": "API endpoint not found"}
    
    # Ищем файл в care_webapp
    file_path = os.path.join(CARE_WEBAPP_DIR, full_path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # Ищем файл в assets
    asset_path = os.path.join(ASSETS_DIR, full_path)
    if os.path.exists(asset_path) and os.path.isfile(asset_path):
        return FileResponse(asset_path)
    
    # Для всех остальных запросов возвращаем index.html (SPA fallback)
    index_path = os.path.join(CARE_WEBAPP_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    
    return {"error": "Not found"}

# ============= КОНЕЦ =============

# Запуск при старте файла
if __name__ == "__main__":
    # Koyeb/Render/etc. прокидывают порт через env, поэтому пробуем PORT/PORT0
    port = int(os.getenv("PORT") or os.getenv("PORT0") or "8000")
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=port,
    )
