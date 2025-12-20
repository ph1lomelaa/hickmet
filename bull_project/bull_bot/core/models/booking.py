from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class MealType(Enum):
    HB = "Завтрак+Ужин"
    BB = "Только завтрак"
    RO = "Без питания"
    NONE = "-"

class RoomType(Enum):
    SGL = "Одноместный"
    DBL = "Двухместный"
    TRPL = "Трёхместный"
    QUAD = "Четырёхместный"

@dataclass
class Booking:
    """Карточка бронирования паломника"""
    id: int = None
    fio: str = ""
    iin: str = ""
    dob: str = ""  # DD.MM.YYYY
    passport_num: str = ""
    visa: str = "Empty"  # Ready/In Process/Pending/Empty
    flight: str = ""  # KC101, KC102 и т.д.
    meal: MealType = MealType.NONE
    room: RoomType = RoomType.DBL
    price: int = 0
    train: str = "-"
    manager: str = ""
    phone: str = ""
    comment: str = ""
    status: str = "Active"  # Active/Completed/Cancelled
    created: str = None  # timestamp

    def to_dict(self):
        return {
            "ID": self.id,
            "ФИО": self.fio,
            "ИИН": self.iin,
            "DOB": self.dob,
            "Passport#": self.passport_num,
            "Visa": self.visa,
            "Flight": self.flight,
            "Meal": self.meal.value,
            "Room": self.room.value,
            "Price": self.price,
            "Train": self.train,
            "Manager": self.manager,
            "Phone": self.phone,
            "Comment": self.comment,
            "Status": self.status,
            "Created": self.created or datetime.now().isoformat(),
        }