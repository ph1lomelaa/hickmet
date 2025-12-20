from aiogram.fsm.state import State, StatesGroup

class BookingStates(StatesGroup):
    # Этап 1: Паспорт
    choosing_table = State()   # Выбор таблицы
    choosing_date = State()    # Выбор листа (даты)
    choosing_pkg = State()
    waiting_for_passport = State()
    confirm_passport_data = State()

    # Этап 2: Виза
    waiting_for_visa = State()

    # Этап 3: Рейс
    waiting_for_flight = State()

    # Этап 4: Питание
    waiting_for_meal = State()

    # Этап 5: Номер
    waiting_for_room = State()

    # Этап 6: Цена
    waiting_for_price = State()

    # Этап 7: Поезд
    waiting_for_train = State()

    # Этап 8: Менеджер
    waiting_for_manager = State()

    # Этап 9: Телефон
    waiting_for_phone = State()

    # Этап 10: Комментарий
    waiting_for_comment = State()

    # Предпросмотр
    preview_booking = State()