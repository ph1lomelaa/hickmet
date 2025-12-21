import os
import re
import json
import logging
from typing import Optional, Dict

from aiogram import Bot, Dispatcher
import gspread
from google.oauth2.service_account import Credentials
from aiogram.client.default import DefaultBotProperties

HOTELS_NAME_HINTS = [
    "hotel", "otel", "отель", "гостиница",
    "makkah", "madinah", "mekka", "medina", "мекка", "медина",
    "shohada", "swiss", "fairmont", "pullman", "zamzam",
    "movempick", "hilton", "conrad", "jabal", "omar",
    "anwar", "dar", "iman", "taiba", "aram", "millennium",
    "front", "view", "city", "tower", "voco", "sheraton",
    "address", "convention", "jumeirah", "marriott",
    "courtyard", "vally", "wof", "sfi"
]

NOISE_TOKENS = [
    "inf", "chd", "child", "baby", "infant", "инфант", "ребенок",
    "no visa", "visa", "ticket", "guide", "гид",
    "total", "price", "room", "dbl", "trpl", "quad", "quin",
    "paid", "free", "cancel", "change", "adult", "pax",
    "sum", "итог", "всего", "makkah", "madinah", "перенос",
    "авиа", "stop sale", "бронь", "bus", "train",
    "ow", "rt", "изменение", "transfer"
]

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
LOGGER = logging.getLogger(__name__)

# ==================== ПУТИ ПРОЕКТА ====================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))      # bull_bot/config
PROJECT_ROOT = os.path.dirname(BASE_DIR)                   # bull_bot

print(f"📍 BASE_DIR: {BASE_DIR}")
print(f"📍 PROJECT_ROOT: {PROJECT_ROOT}")

# Директории (абсолютные пути для файловой системы)
ABS_TMP_DIR = os.path.join(PROJECT_ROOT, "tmp")
ABS_UPLOADS_DIR = os.path.join(ABS_TMP_DIR, "uploads")
ABS_BOOKING_CARDS_DIR = os.path.join(ABS_TMP_DIR, "booking_cards")
CREDENTIALS_DIR = os.path.join(PROJECT_ROOT, "credentials")

os.makedirs(ABS_UPLOADS_DIR, exist_ok=True)
os.makedirs(ABS_BOOKING_CARDS_DIR, exist_ok=True)
os.makedirs(CREDENTIALS_DIR, exist_ok=True)
# === 🔑 КЛЮЧИ (Вот эта часть у тебя пропала) ===
CREDENTIALS_DIR = os.path.join(PROJECT_ROOT, "credentials")
# Имя файла ключа (должно совпадать с тем, как ты назвала файл в папке credentials)
CREDENTIALS_FILE = os.path.join(CREDENTIALS_DIR, "service_account.json")
# ==================== РЕЖИМ РАБОТЫ ====================
MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "false"
print(f"🔧 MOCK_MODE: {MOCK_MODE}")

# ==================== TELEGRAM ====================

API_TOKEN = os.getenv("API_TOKEN", "8078089873:AAGi5ApT1uyFLCN8YWkkyuWGMwSuxEBh-84")


if not API_TOKEN or API_TOKEN.startswith("your_"):
    LOGGER.warning("⚠️ API_TOKEN не установлен или тестовый")

try:
    bot = Bot(
        token=API_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()
    LOGGER.info("✅ Bot инициализирован")
except Exception as e:
    LOGGER.error(f"❌ Ошибка инициализации Bot: {e}")
    bot = None
    dp = None

# ==================== GOOGLE SHEETS ====================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

client: Optional[gspread.Client] = None
gs: Optional[gspread.Client] = None

if MOCK_MODE:
    LOGGER.info("📋 MOCK режим активирован - Google Sheets не требуется")
else:
    LOGGER.info("📋 Попытка подключения к Google Sheets...")

    creds: Optional[Credentials] = None
    json_config = os.getenv("GOOGLE_CREDS_JSON")

    if json_config:
        LOGGER.info("✅ Ключи найдены в переменной окружения GOOGLE_CREDS_JSON")
        try:
            creds_dict = json.loads(json_config)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        except Exception as e:
            LOGGER.error(f"❌ Ошибка парсинга GOOGLE_CREDS_JSON: {e}")
            creds = None

    if not json_config:
        # Пробуем файл
        CREDENTIALS_FILE = os.path.join(
            CREDENTIALS_DIR,
            "service_account.json",
        )
        LOGGER.info(f"🔍 Ищем файл ключей: {CREDENTIALS_FILE}")

        if os.path.exists(CREDENTIALS_FILE):
            LOGGER.info("✅ Файл ключей найден")
            try:
                creds = Credentials.from_service_account_file(
                    CREDENTIALS_FILE,
                    scopes=SCOPES,
                )
            except Exception as e:
                LOGGER.error(f"❌ Ошибка чтения файла ключей: {e}")
                creds = None
        else:
            LOGGER.warning(
                f"⚠️ Файл ключей не найден: {CREDENTIALS_FILE}\n"
                f"📌 Для использования Google Sheets:\n"
                f"   1. Скачайте ключи из Google Cloud Console\n"
                f"   2. Поместите JSON файл в: {CREDENTIALS_DIR}/\n"
                f"   3. Или установите переменную GOOGLE_CREDS_JSON\n"
                f"💡 Пока Google Sheets недоступен"
            )

    if creds is not None:
        try:
            client = gspread.authorize(creds)
            gs = client
            LOGGER.info("✅ Google Sheets подключен")
        except Exception as e:
            LOGGER.error(f"❌ Ошибка подключения к Google Sheets: {e}")
            client = None
            gs = None
    else:
        LOGGER.warning("⚠️ Нет валидных Credentials, Google Sheets отключён")

# ==================== ПРОЧИЕ ПУТИ / НАСТРОЙКИ ====================

ADMIN_PASSWORD = "HickmetTravel"
MANAGER_PASSWORD = "SALE"
CARE_PASSWORD = "CARE"

FONTS_DIR = os.path.join(PROJECT_ROOT, "assets", "fonts", "Montserrat", "static")
TTF_REGULAR = os.path.join(FONTS_DIR, "Montserrat-Regular.ttf")
TTF_BOLD = os.path.join(FONTS_DIR, "Montserrat-Bold.ttf")

# Poppler (для pdf2image на macOS)
POPPLER_PATH = os.getenv("POPPLER_PATH", "/opt/homebrew/bin")

# Относительные пути — как раньше (чтобы старый код не сломать)
TMP_DIR = "tmp/"
UPLOADS_DIR = "tmp/uploads/"
BOOKING_CARDS_DIR = "tmp/booking_cards/"

# ==================== REGEX И СЛУЖЕБНЫЕ КОНСТАНТЫ ====================

IIN_RX = re.compile(r"\b\d{12}\b")          # Казахстанский ИИН
PASSPORT_NUM_RX = re.compile(r"^[A-Z]{2}\d{7}$")
PHONE_RX = re.compile(r"^\+?[\d\s\-()]{10,}$")

EXCLUDE_SHEETS = [
    "Доп услуги", "Подлетки", "расписание рейсов",
    "Рейсы с пакетами", "AUGUST 2025", "Лист16",
]

MONTHS_RU = {
    "January": "JANUARY", "February": "FEBRUARY", "March": "MARCH",
    "April": "APRIL", "May": "MAY", "June": "JUNE",
    "July": "JULY", "August": "AUGUST", "September": "SEPTEMBER",
    "October": "OCTOBER", "November": "NOVEMBER", "December": "DECEMBER",
}

DATE_ANY = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})")
DATE_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

PACKAGE_NAMES = [
    "NIYET ECONOM 7 DAYS", "NIYET 7 DAYS", "HIKMA 7 DAYS",
    "IZI SWISSOTEL", "IZI FAIRMONT", "4 YOU",
    "NIYET акционный 7 DAYS", "NIYET 11 DAYS",
    "HIKMA 11 DAYS", "AMAL 11 DAYS",
    "PARK REGIS 7 DAYS", "IZI 7 DAYS",
]

ROOM_HUMAN_RU = {
    "SGL":  "Одноместный номер",
    "DBL":  "Двухместный номер",
    "TWIN": "Двухместный номер (twin)",
    "TRPL": "Трёхместный номер",
    "QUAD": "Четырёхместный номер",
}

RANGE_RE = re.compile(
    r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})\s*[–—-]\s*(\d{1,2})[.\-/](\d{1,2})(?!\d)"
)
HEADER_HINTS = {"№", "No", "N°"}

BUS_WORD = re.compile(r"(?i)\b(bus|автобус)\b")
DDMM_RE = re.compile(r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})(?!\d)")

FLIGHT_RE = re.compile(r"\bKC\s*?(\d{3,4})\b", re.IGNORECASE)
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")

SECOND_ASSETS = {
    "UAEmed":       "uae-med.png",
    "UAEmec":       "uae-mec.png",
    "JEDMED_TRAIN": "jed-med-train.png",
}

_XLSX_PATH = "OCTOBER 2025.xlsx"
_HOTELS_HINTS = ("hotel", "hotels", "отель", "отели", "размещение", "accommodation")

TRAIN_RE = re.compile(r"\b(train|Поезд|жд)\b", re.I)
BUS_RE = re.compile(r"\b(bus|автобус)\b", re.I)
TRANSFER_RE = re.compile(r"\b(transfer|трансфер)\b", re.I)
ROUTE_RE = re.compile(r"\b([A-Z]{3})\s*[-–/]\s*([A-Z]{3})\b", re.I)

NEXT_PACKAGE_HINT = re.compile(
    r"(\d{1,2}[./-]\d{1,2}\s*[–—-]\s*\d{1,2}[./-]\d{1,2})"
    r"|(niyet|hikma|izi|amal)\s*(\d+)?\s*(?:days|d)\b",
    re.I,
)

# === PREVIEW / EDIT STATE ===
PREVIEW_CACHE: Dict[str, dict] = {}   # cache_id -> {...}
EDIT_STATE: Dict[int, dict] = {}      # user_id -> {...}

# === КООРДИНАТЫ ДЛЯ ОТРИСОВКИ ВАУЧЕРА (стр. 1) ===
DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})\b")

BG_PATH = "v1.png"
TTF_PATH = os.path.join(
    PROJECT_ROOT,
    "fonts",
    "Montserrat",
    "static",
    "Montserrat-Regular.ttf",
)
BG_UAE_MED = "uae-med.png"
BG_UAE_MEC = "uae-mec.png"
BG_JED_MED_TRAIN = "jed-med-train.png"

# === ГОРОДА ===
CITY_ALIASES = {
    "madinah": ["madinah", "medinah", "medina", "madina", "mdinah", "mdina", "мадина", "медина"],
    "makkah": ["makkah", "makka", "mecca", "mekka", "makah", "макка", "мекка"],
}

CITY_ALIASES_HOTELS = {
    "madinah": ["madinah", "medinah", "medina", "madina", "мадина", "медина"],
    "makkah": ["makkah", "makka", "mecca", "мекка", "макка"],
    "jeddah": ["jeddah", "jed", "джедда", "джидда", "джеддаh"],
    "alula": ["al ula", "al-ula", "alula", "аль-ула", "алула"],
}
CITY_PRIORITY = ["madinah", "makkah", "jeddah", "alula"]

PKG_KIND_ALIASES = {
    "niyet": [
        "niyet", "ниет", "niyet economy", "niyet econom",
        "акцион", "акция", "акционный", "akcion",
    ],
    "niyet/7d": ["niyet/7d", "niyet 7 days"],
    "niyet/10d": ["niyet /10 d"],
    "hikma": ["hikma", "хикма"],
    "izi": [
        "izi", "izi swissotel", "izi fairmont", "izi 4u", "izi 4 you",
        "4 you", "4you", "4u", "swiss/4 you",
        "4 you shohada", "amal", "амал",
    ],
    "aroya": ["aroya", "ароя", "arоya", "aroya only"],
    "aa": ["aa", "aa/7days", "aa/7 days"],
    "shohada": ["shohada"],
    "aktau": ["aktau"],
    "nqz": ["nqz"],
    "sco-med": ["sco-med", "sco med"],
    "ala-jed": ["ala-jed", "ala-med", "jed-med", "med-jed", "med-mak", "mak-med"],
    "standard": ["standard"],
}

NAME_COMBINED_RE = re.compile(r"\b(фио|имя\s*и\s*фамилия|guest.?name|name)\b", re.I)
FIRST_NAME_RE = re.compile(r"\b(имя|first.?name)\b", re.I)
LAST_NAME_RE = re.compile(r"\b(фамилия|last.?name|surname)\b", re.I)
ROOM_COL_RE = re.compile(
    r"\b(type\s*of\s*room|room\s*type|тип\s*номера|тип\s*размещения)\b", re.I
)

PEOPLE_STOP_RE = re.compile(r"\b(bus|train|transfer|трансфер)\b", re.I)
PKG_TITLE_RE = re.compile(r"\b(niyet|hikma|amal|izi|aroya|aa)\b", re.I)
HEADER_CELL_RE = re.compile(r"^\s*№\s*$", re.I)

ROOM_PATTERNS = [
    ("QUAD", 4, re.compile(r"\b(quad|quadro|quadruple|квадр|квад|4\s*-?\s*мест|4pax)\b", re.I)),
    ("TRPL", 3, re.compile(r"\b(trpl|triple|tpl|трипл|3\s*-?\s*мест)\b", re.I)),
    ("TWIN", 2, re.compile(r"\b(twin|twn)\b", re.I)),
    ("DBL", 2, re.compile(r"\b(dbl|double|двойн|2\s*-?\s*мест)\b", re.I)),
    ("SGL", 1, re.compile(r"\b(sgl|single|одномест|1\s*-?\s*мест|single\s*use)\b", re.I)),
]

HDR_ALIASES = {
    "room": ("type of room", "room type", "тип номера", "тип размещения", "room"),
    "last": ("last name", "фамилия", "surname"),
    "first": ("first name", "имя"),
    "name": ("name", "guest name", "guestname", "фио", "имя и фамилия"),
    "meal": ("meal a day", "meal", "питание"),
    "gender": ("gender", "sex", "пол", "м/ж", "m/f"),
}

CAP = {"quad": 4, "trpl": 3, "dbl": 2, "twin": 2, "sgl": 1}
ROOM_ALIASES = {
    "quad": ("quad", "quadro", "quadruple", "quard", "quattro", "квадр"),
    "trpl": ("trpl", "triple", "tpl", "трипл", "трпл"),
    "twin": ("twin", "twn"),
    "dbl": ("dbl", "double", "дабл", "дбл"),
    "sgl": ("sgl", "single", "single use", "одномест"),
}

INF_RX = re.compile(r"\binf\b", re.I)

_FAMILY_EQUIV = {
    frozenset(("4u", "amal")),
}

HOTELS_TITLE_RE = re.compile(r"(?i)\b(hotel|hotels|отел[ьи]|размещени[ея]|accommod)\b")

STOP_HINTS = (
    "transfer", "train", "bus", "guide", "гид", "трансфер", "ow",
)

DATE_RANGE_RX = re.compile(
    r"\b(\d{1,2})/(\d{1,2})/(\d{4})\s*[–—-]\s*(\d{1,2})/(\d{1,2})/(\d{4})\b"
)

SERVICE_HINTS = re.compile(
    r"(?i)\b(transfer|train|bus|yes\s*tour|комиссия|итог|таблица)\b"
)



DATE_TOKEN_RX = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}")
NOISE_TOKENS = {
    "makkah", "madinah", "перенос", "авиа", "stop sale", "бронь", "bus", "train",
    "ow", "rt", "изменение", "transfer",
}

CHILD_RX = re.compile(r"\b(inf(ant)?|chd|child|kid|реб(ён|ен)ок|дет(и|ск))\b", re.I)
# =========================================================
# ВСТАВИТЬ В САМЫЙ КОНЕЦ ФАЙЛА constants.py
# (Это гарантирует, что списки будут заполнены)
# =========================================================

HOTELS_NAME_HINTS = [
    "hotel", "otel", "отель", "гостиница",
    "makkah", "madinah", "mekka", "medina", "мекка", "медина",
    "shohada", "swiss", "fairmont", "pullman", "zamzam",
    "movempick", "hilton", "conrad", "jabal", "omar",
    "anwar", "dar", "iman", "taiba", "aram", "millennium",
    "front", "view", "city", "tower", "voco", "sheraton",
    "address", "convention", "jumeirah", "marriott",
    "courtyard", "vally", "wof", "sfi"
]

NOISE_TOKENS = [
    "inf", "chd", "child", "baby", "infant", "инфант", "ребенок",
    "no visa", "visa", "ticket", "guide", "гид",
    "total", "price", "room", "dbl", "trpl", "quad", "quin",
    "paid", "free", "cancel", "change", "adult", "pax",
    "sum", "итог", "всего"
]

# На всякий случай дублируем регулярки, если их нет
try:
    DATE_TOKEN_RX
except NameError:
    import re
    DATE_TOKEN_RX = re.compile(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}')
    DDMM_RE = re.compile(r'\d{1,2}[./-]\d{1,2}')
