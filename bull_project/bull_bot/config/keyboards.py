from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==================== РОЛЕВЫЕ МЕНЮ (ГЛАВНЫЕ) ====================

def manager_kb():
    """Меню для Менеджера (Продажи)"""
    from aiogram.types import WebAppInfo
    HISTORY_URL = "https://ph1lomelaa.github.io/book/history_v2.html"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Создать бронь", callback_data="create_booking")],
        [InlineKeyboardButton(text="История бронирования", web_app=WebAppInfo(url=HISTORY_URL))],
    ])

def care_kb():
    """Меню для Отдела Заботы"""
    from aiogram.types import WebAppInfo

    CARE_BOOKINGS_URL = "https://ph1lomelaa.github.io/book/admin-bookings.html"
    CARE_SEARCH_URL = "https://ph1lomelaa.github.io/book/search-pilgrim.html"
    CARE_PACKAGES_URL = "https://ph1lomelaa.github.io/book/package-lists.html"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Список броней", web_app=WebAppInfo(url=CARE_BOOKINGS_URL))],
        [InlineKeyboardButton(text="Найти паломника", web_app=WebAppInfo(url=CARE_SEARCH_URL))],
        [InlineKeyboardButton(text="Списки по пакетам", web_app=WebAppInfo(url=CARE_PACKAGES_URL))],
    ])

def admin_kb():
    from aiogram.types import WebAppInfo
    ADMIN_PANEL_URL = "https://ph1lomelaa.github.io/book/admin-panel.html"
    ADMIN_BOOKINGS_URL = "https://ph1lomelaa.github.io/book/admin-bookings.html"
    ADMIN_REQUESTS_URL = "https://ph1lomelaa.github.io/book/admin-requests.html"
    CARE_SEARCH_URL = "https://ph1lomelaa.github.io/book/search-pilgrim.html"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Аналитика", web_app=WebAppInfo(url=ADMIN_PANEL_URL))],
        [InlineKeyboardButton(text="Список броней", web_app=WebAppInfo(url=ADMIN_BOOKINGS_URL))],
        [InlineKeyboardButton(text="Создать бронь", callback_data="create_booking")],
        [InlineKeyboardButton(text="Найти паломника", web_app=WebAppInfo(url=CARE_SEARCH_URL))],
        [InlineKeyboardButton(text="Запросы на отмену/перенос", web_app=WebAppInfo(url=ADMIN_REQUESTS_URL))],
        [InlineKeyboardButton(text="Запросы 4U", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔔 Настройки уведомлений", callback_data="admin_notify_menu")]
    ])

from aiogram.utils.keyboard import InlineKeyboardBuilder

def search_results_kb(results):
    builder = InlineKeyboardBuilder()

    for res in results:
        pass
        # (Логику генерации реализуем прямо в handler для надежности, см. ниже)

    return builder.as_markup()

def get_menu_by_role(role: str) -> InlineKeyboardMarkup:
    """
    Эта функция решает, какое меню показать человеку
    в зависимости от его роли в Базе Данных.
    """
    if role == "admin":
        return admin_kb()
    elif role == "care":
        return care_kb()
    else:
        return manager_kb() # По умолчанию показываем меню менеджера

# ==================== КЛАВИАТУРЫ GOOGLE SHEETS ====================

def kb_select_table(tables: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for name, sheet_id in tables.items():
        builder.button(text=name, callback_data=f"sel_tab:{sheet_id}")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()

def kb_select_sheet(sheets: list, has_more: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for sheet_name in sheets:
        builder.button(text=sheet_name, callback_data=f"sel_date:{sheet_name}")

    if has_more:
        builder.button(text="⬇️ Показать все", callback_data="show_all_dates")

    builder.button(text="🔙 Назад", callback_data="back_to_tables")
    builder.adjust(1)
    return builder.as_markup()

def kb_select_package(packages: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # Кнопки пакетов
    for row_id, pkg_name in packages.items():
        builder.button(text=pkg_name, callback_data=f"sel_pkg:{row_id}")

    # Спец. кнопка
    builder.button(text="🔵 Запросить пакет 4U", callback_data="req_4u")

    builder.button(text="🔙 Назад", callback_data="back_to_dates")
    builder.adjust(1)
    return builder.as_markup()

# ==================== КЛАВИАТУРЫ АНКЕТЫ ====================

def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Верно", callback_data="confirm_yes")],
        [InlineKeyboardButton(text="❌ Переснять", callback_data="confirm_no")],
    ])

train_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text=" YES", callback_data="train_yes"),
     InlineKeyboardButton(text=" NO", callback_data="train_no")]
])
def visa_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оставить пустым", callback_data="visa_Empty")],
    ])

def meal_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=" HB ", callback_data="meal_HB")],
        [InlineKeyboardButton(text=" BB ", callback_data="meal_BB")],
        [InlineKeyboardButton(text=" RO ", callback_data="meal_RO")],
    ])

def room_kb():
    builder = InlineKeyboardBuilder()
    # Ваши варианты
    builder.button(text="Quadro", callback_data="room_QUAD")
    builder.button(text="Triple", callback_data="room_TRPL")
    builder.button(text="Double", callback_data="room_DBL")
    builder.button(text="Single", callback_data="room_SGL")
    # Доп
    builder.button(text="INF", callback_data="room_INF")
    builder.button(text="CHILD", callback_data="room_CHILD")
    builder.adjust(2)
    return builder.as_markup()

def placement_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=" Произвольное размещение", callback_data="place_random")],
        [InlineKeyboardButton(text=" Разместить с человеком", callback_data="place_specific")],
    ])

def comment_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="skip_comment")],
    ])

def preview_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить", callback_data="save_booking")],
        [InlineKeyboardButton(text="🔄 Заново", callback_data="main_menu")],
    ])

def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])

def main_menu_kb():
    # Эта функция оставлена для совместимости, если где-то еще вызывается,
    # но лучше использовать get_menu_by_role
    return manager_kb()

def yes_no_kb(text="Пропустить"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data="skip")],
    ])
def count_kb():
    """Клавиатура для выбора количества паломников"""
    builder = InlineKeyboardBuilder()
    # Кнопки 1-10
    for i in range(1, 11):
        builder.button(text=str(i), callback_data=f"count_{i}")
    builder.adjust(5) # По 5 в ряд
    return builder.as_markup()

def family_or_separate_kb():
    """Выбор типа размещения для группы"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍👩‍👧 ВМЕСТЕ (Семья)", callback_data="place_family")],
        [InlineKeyboardButton(text="🚻 РАЗДЕЛЬНО (М/Ж)", callback_data="place_separate")],
    ])
