"""
table_parser.py - Парсинг структуры таблиц бронирования
"""
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import re
import logging

logger = logging.getLogger(__name__)

@dataclass
class TableRow:
    """Строка таблицы"""
    row_index: int  # Индекс строки (0-based в данных Google Sheets)
    type_of_room: Optional[str]  # QUADRO/TRIPLE/DOUBLE/SINGLE/INF/CHILD
    last_name: str
    first_name: str
    gender: str  # M/F/пусто
    is_occupied: bool
    room_capacity: int = 0  # Вместимость комнаты
    raw_data: List[str] = None  # Оригинальные данные строки

@dataclass
class PackageStructure:
    """Структура пакета в таблице"""
    package_name: str
    start_row: int  # Строка с названием пакета (0-based)
    end_row: int  # Строка перед следующим пакетом (0-based)
    rows: List[TableRow]
    available_by_gender: Dict[str, List[int]]  # Свободные места по полу {M: [row1, row2], F: [...]}
    available_by_room: Dict[str, List[int]]  # Свободные места по типу комнаты

class TableParser:
    """Парсер для работы с таблицами бронирования Google Sheets"""

    # Индексы колонок по вашей структуре (смотрим на PDF)
    COLUMN_INDICES = {
        "number": 0,        # №
        "visa": 1,          # VISA
        "avia": 2,          # Avia
        "room_type": 3,     # Type of room
        "meal": 4,          # Meal a day
        "last_name": 5,     # Last Name
        "first_name": 6,    # First Name
        "gender": 7,        # Gender
        "dob": 8,           # Date of Birth
        "doc_number": 9,    # Document Number
        "doc_expiry": 10,   # Document Expiration
        "price": 11,        # Price
        "comment": 12,      # Comment
        "manager": 13,      # Manager
        "train": 14,        # Train
    }

    # Вместимость комнат
    ROOM_CAPACITY = {
        "QUADRO": 4,
        "TRIPLE": 3,
        "DOUBLE": 2,
        "SINGLE": 1,
        "INF": 1,
        "CHILD": 1,
    }

    # Алиасы типов комнат
    ROOM_ALIASES = {
        "QUADRO": ["quadro", "quad", "4", "квадро", "четырехместный"],
        "TRIPLE": ["triple", "tripl", "3", "тройной", "трехместный"],
        "DOUBLE": ["double", "dbl", "2", "двойной", "двухместный"],
        "SINGLE": ["single", "sgl", "1", "одиночный", "одноместный"],
        "INF": ["inf", "infant", "младенец", "инфант"],
        "CHILD": ["child", "chd", "ребенок", "детский"],
    }

    def parse_sheet_data(self, sheet_data: List[List[str]]) -> List[PackageStructure]:
        """
        Парсит весь лист на пакеты

        Args:
            sheet_data: Данные листа из Google Sheets (список строк)

        Returns:
            Список найденных пакетов
        """
        packages = []
        current_package = None
        current_room_type = None  # Текущий тип комнаты для наследования

        logger.info(f"Парсим лист с {len(sheet_data)} строками")

        for row_idx, row in enumerate(sheet_data):
            # Пропускаем полностью пустые строки
            if not row or all(str(cell).strip() == "" for cell in row):
                if current_package and current_room_type:
                    # Сохраняем текущий тип комнаты для следующей строки
                    pass
                continue

            # Проверяем, является ли строка заголовком пакета
            if self._is_package_header(row):
                logger.info(f"Найден заголовок пакета в строке {row_idx}: {row}")

                # Закрываем предыдущий пакет
                if current_package:
                    current_package.end_row = row_idx - 1
                    self._update_package_availability(current_package)
                    packages.append(current_package)
                    logger.info(f"Пакет '{current_package.package_name}' закрыт (строки {current_package.start_row}-{current_package.end_row})")

                # Начинаем новый пакет
                package_name = self._extract_package_name(row)
                current_package = PackageStructure(
                    package_name=package_name,
                    start_row=row_idx,
                    end_row=len(sheet_data) - 1,  # Временное значение
                    rows=[],
                    available_by_gender={"M": [], "F": []},
                    available_by_room={}
                )
                current_room_type = None  # Сбрасываем тип комнаты для нового пакета
                continue

            # Если есть активный пакет, парсим строку таблицы
            if current_package:
                table_row = self._parse_table_row(row, row_idx, current_room_type)
                if table_row:
                    current_package.rows.append(table_row)
                    # Обновляем текущий тип комнаты для наследования
                    if table_row.type_of_room:
                        current_room_type = table_row.type_of_room

        # Закрываем последний пакет
        if current_package:
            current_package.end_row = len(sheet_data) - 1
            self._update_package_availability(current_package)
            packages.append(current_package)
            logger.info(f"Последний пакет '{current_package.package_name}' закрыт")

        logger.info(f"Всего найдено пакетов: {len(packages)}")
        return packages

    def _is_package_header(self, row: List[str]) -> bool:
        """Проверяет, является ли строка заголовком пакета"""
        if not row:
            return False

        # Объединяем первые несколько ячеек для проверки
        header_text = " ".join(str(cell) for cell in row[:3] if cell).strip()

        # Ищем паттерн дат в начале: dd.mm-dd.mm
        date_pattern = r'\d{1,2}\.\d{1,2}\s*[-–]\s*\d{1,2}\.\d{1,2}'
        has_dates = bool(re.search(date_pattern, header_text))

        # Ищем ключевые слова пакетов
        has_package_keywords = any(
            keyword in header_text.lower()
            for keyword in ["niyet", "hikma", "izi", "4u", "amal", "aroya", "7d", "10d"]
        )

        return has_dates and has_package_keywords

    def _extract_package_name(self, row: List[str]) -> str:
        """Извлекает название пакета из заголовка"""
        if not row:
            return ""

        # Берем первую непустую ячейку
        for cell in row:
            cell_str = str(cell).strip()
            if cell_str:
                return cell_str
        return ""

    def _parse_table_row(
            self,
            row: List[str],
            row_idx: int,
            current_room_type: Optional[str]
    ) -> Optional[TableRow]:
        """Парсит строку таблицы"""
        # Минимальная проверка - должна быть хотя бы колонка Last Name
        if len(row) <= self.COLUMN_INDICES["last_name"]:
            return None

        # Определяем тип комнаты
        room_type = None
        room_type_idx = self.COLUMN_INDICES["room_type"]

        if len(row) > room_type_idx:
            room_type_cell = row[room_type_idx]
            if room_type_cell and str(room_type_cell).strip():
                room_type = self._normalize_room_type(str(room_type_cell))

        # Если тип комнаты не указан, наследуем текущий
        if not room_type and current_room_type:
            room_type = current_room_type

        # Получаем данные паломника
        last_name_idx = self.COLUMN_INDICES["last_name"]
        first_name_idx = self.COLUMN_INDICES["first_name"]
        gender_idx = self.COLUMN_INDICES["gender"]

        last_name = ""
        if len(row) > last_name_idx:
            last_name = str(row[last_name_idx] or "").strip()

        first_name = ""
        if len(row) > first_name_idx:
            first_name = str(row[first_name_idx] or "").strip()

        gender = ""
        if len(row) > gender_idx:
            gender_cell = row[gender_idx]
            if gender_cell:
                gender = self._normalize_gender(str(gender_cell))

        # Определяем занятость (есть ли фамилия)
        is_occupied = bool(last_name)

        # Определяем вместимость комнаты
        capacity = 0
        if room_type:
            capacity = self.ROOM_CAPACITY.get(room_type.upper(), 0)

        table_row = TableRow(
            row_index=row_idx,
            type_of_room=room_type,
            last_name=last_name,
            first_name=first_name,
            gender=gender,
            is_occupied=is_occupied,
            room_capacity=capacity,
            raw_data=row.copy()
        )

        return table_row

    def _normalize_room_type(self, room_type: str) -> Optional[str]:
        """Нормализует тип комнаты"""
        if not room_type:
            return None

        room_lower = room_type.lower().strip()

        for normalized_type, aliases in self.ROOM_ALIASES.items():
            for alias in aliases:
                if alias in room_lower:
                    return normalized_type

        # Числовые обозначения
        if "4" in room_lower:
            return "QUADRO"
        elif "3" in room_lower:
            return "TRIPLE"
        elif "2" in room_lower:
            return "DOUBLE"
        elif "1" in room_lower:
            return "SINGLE"

        return room_type.upper()

    def _normalize_gender(self, gender: str) -> str:
        """Нормализует гендер"""
        if not gender:
            return ""

        gender_lower = gender.lower().strip()

        if gender_lower in ["m", "м", "male", "муж", "мужской"]:
            return "M"
        elif gender_lower in ["f", "ж", "female", "жен", "женский"]:
            return "F"

        return ""

    def _update_package_availability(self, package: PackageStructure):
        """Обновляет информацию о свободных местах в пакете"""
        # Сбрасываем списки
        package.available_by_gender = {"M": [], "F": []}
        package.available_by_room = {}

        for row in package.rows:
            if not row.is_occupied:
                # Добавляем по гендеру
                if row.gender == "M":
                    package.available_by_gender["M"].append(row.row_index)
                elif row.gender == "F":
                    package.available_by_gender["F"].append(row.row_index)
                else:
                    # Если гендер не указан, добавляем в оба
                    package.available_by_gender["M"].append(row.row_index)
                    package.available_by_gender["F"].append(row.row_index)

                # Добавляем по типу комнаты
                if row.type_of_room:
                    if row.type_of_room not in package.available_by_room:
                        package.available_by_room[row.type_of_room] = []
                    package.available_by_room[row.type_of_room].append(row.row_index)

class SpotFinder:
    """Поиск свободных мест в таблице"""

    def __init__(self, parser: TableParser):
        self.parser = parser

    def find_available_spot(
            self,
            sheet_data: List[List[str]],
            package_name: str,
            gender: str,
            preferred_room_type: str = None
    ) -> Optional[Tuple[int, str]]:
        """
        Находит свободное место в пакете

        Args:
            sheet_data: Данные листа
            package_name: Название пакета (или часть названия)
            gender: Пол паломника (M/F)
            preferred_room_type: Желаемый тип комнаты (QUADRO/TRIPLE/DOUBLE и т.д.)

        Returns:
            (row_index, found_room_type) или None
        """
        logger.info(f"Поиск места: пакет='{package_name}', пол='{gender}', тип='{preferred_room_type}'")

        # Парсим все пакеты в листе
        packages = self.parser.parse_sheet_data(sheet_data)

        # Находим нужный пакет (по частичному совпадению)
        target_package = None
        search_name = package_name.lower()

        for pkg in packages:
            if search_name in pkg.package_name.lower():
                target_package = pkg
                logger.info(f"Найден пакет: '{pkg.package_name}' (строки {pkg.start_row}-{pkg.end_row})")
                break

        if not target_package:
            logger.error(f"Пакет '{package_name}' не найден")
            return None

        # Стратегия 1: Ищем в указанном типе комнаты
        if preferred_room_type:
            normalized_preferred = self.parser._normalize_room_type(preferred_room_type)

            if normalized_preferred and normalized_preferred in target_package.available_by_room:
                for row_idx in target_package.available_by_room[normalized_preferred]:
                    # Проверяем, что строка существует
                    if row_idx < len(sheet_data):
                        row = sheet_data[row_idx]

                        # Проверяем гендер в строке
                        gender_idx = self.parser.COLUMN_INDICES["gender"]
                        row_gender = ""
                        if len(row) > gender_idx:
                            row_gender = self.parser._normalize_gender(str(row[gender_idx]))

                        # Место подходит если гендер совпадает или не указан
                        if not row_gender or row_gender == gender:
                            # Дополнительно проверяем, что фамилия действительно пустая
                            last_name_idx = self.parser.COLUMN_INDICES["last_name"]
                            last_name = ""
                            if len(row) > last_name_idx:
                                last_name = str(row[last_name_idx] or "").strip()

                            if not last_name:
                                logger.info(f"Найдено место в {normalized_preferred}: строка {row_idx}")
                                return row_idx, normalized_preferred

        # Стратегия 2: Ищем любое место с подходящим гендером
        available_rows = target_package.available_by_gender.get(gender, [])

        for row_idx in available_rows:
            if row_idx < len(sheet_data):
                row = sheet_data[row_idx]

                # Проверяем, что место действительно свободно
                last_name_idx = self.parser.COLUMN_INDICES["last_name"]
                last_name = ""
                if len(row) > last_name_idx:
                    last_name = str(row[last_name_idx] or "").strip()

                if not last_name:
                    # Определяем тип комнаты для этой строки
                    room_type = None
                    for row_obj in target_package.rows:
                        if row_obj.row_index == row_idx:
                            room_type = row_obj.type_of_room
                            break

                    if not room_type:
                        # Пытаемся определить из данных строки
                        room_type_idx = self.parser.COLUMN_INDICES["room_type"]
                        if len(row) > room_type_idx:
                            room_type_cell = row[room_type_idx]
                            if room_type_cell:
                                room_type = self.parser._normalize_room_type(str(room_type_cell))

                    logger.info(f"Найдено место (любое): строка {row_idx}, тип {room_type}")
                    return row_idx, room_type or "UNKNOWN"

        logger.warning(f"Не найдено свободных мест для пола '{gender}' в пакете '{package_name}'")
        return None

    def get_room_availability_stats(
            self,
            sheet_data: List[List[str]],
            package_name: str
    ) -> Dict[str, Dict[str, int]]:
        """
        Возвращает статистику по доступным местам

        Returns:
            {
                "M": {"QUADRO": 2, "TRIPLE": 1, ...},
                "F": {"QUADRO": 3, "DOUBLE": 2, ...}
            }
        """
        packages = self.parser.parse_sheet_data(sheet_data)

        # Находим нужный пакет
        target_package = None
        search_name = package_name.lower()

        for pkg in packages:
            if search_name in pkg.package_name.lower():
                target_package = pkg
                break

        if not target_package:
            return {"M": {}, "F": {}}

        # Собираем статистику
        stats = {"M": {}, "F": {}}

        for row in target_package.rows:
            if not row.is_occupied and row.type_of_room:
                room_type = row.type_of_room.upper()

                # Если гендер указан
                if row.gender == "M":
                    if room_type not in stats["M"]:
                        stats["M"][room_type] = 0
                    stats["M"][room_type] += 1
                elif row.gender == "F":
                    if room_type not in stats["F"]:
                        stats["F"][room_type] = 0
                    stats["F"][room_type] += 1
                else:
                    # Если гендер не указан, считаем для обоих
                    for gender in ["M", "F"]:
                        if room_type not in stats[gender]:
                            stats[gender][room_type] = 0
                        stats[gender][room_type] += 1

        return stats

# Синглтон для использования
table_parser = TableParser()
spot_finder = SpotFinder(table_parser)