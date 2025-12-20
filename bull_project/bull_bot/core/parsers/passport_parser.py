import cv2
import pytesseract
import numpy as np
from pdf2image import convert_from_path
from PIL import Image
import os
import re
from dataclasses import dataclass
from datetime import datetime

@dataclass
class PassportData:
    """Структура данных паспорта"""
    last_name: str = ""
    first_name: str = ""
    gender: str = ""
    dob: str = ""
    iin: str = ""
    document_number: str = ""
    expiration_date: str = ""
    phone: str = ""  # Добавлено для телефона

    @property
    def full_name(self) -> str:
        return f"{self.last_name} {self.first_name}".strip()

    @property
    def is_valid(self) -> bool:
        """Проверка минимальной валидности данных"""
        has_name = bool(self.last_name or self.first_name)
        has_iin = len(self.iin) == 12 if self.iin else False
        has_doc = bool(self.document_number)
        # Считаем валидным если есть хотя бы имя И (ИИН ИЛИ документ)
        return has_name and (has_iin or has_doc)

    def to_dict(self) -> dict:
        """Возвращает данные в формате для API"""
        return {
            "last_name": self.last_name or "-",
            "first_name": self.first_name or "-",
            "gender": self.gender or "M",
            "date_of_birth": self.dob or "-",
            "passport_num": self.document_number or "-",
            "phone": self.phone or "-",
            # Дополнительные поля для совместимости
            "Last Name": self.last_name or "-",
            "First Name": self.first_name or "-",
            "Gender": self.gender or "M",
            "Date of Birth": self.dob or "-",
            "Document Number": self.document_number or "-",
            "Document Expiration": self.expiration_date or "-",
            "IIN": self.iin or "-",
        }

class PassportParser:
    def __init__(self, poppler_path: str = None, debug: bool = False):
        self.poppler_path = poppler_path
        self.debug = debug
        self._date_cleaner = re.compile(r"\s+")

    def _clean_date(self, value: str) -> str:
        """Удаляет лишние пробелы и нормализует разделители."""
        if not value:
            return ""
        stripped = self._date_cleaner.sub("", value)
        stripped = stripped.replace('/', '.').replace('-', '.')
        if len(stripped) == 8 and stripped.isdigit():
            return f"{stripped[0:2]}.{stripped[2:4]}.{stripped[4:]}"
        return stripped

    def preprocess_image(self, image: Image.Image) -> np.ndarray:
        """Улучшение качества изображения"""
        img = np.array(image)
        if len(img.shape) == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # CLAHE для улучшения контраста
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Дополнительная бинаризация для лучшего распознавания
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return binary

    def extract_ocr_text(self, file_path: str) -> str:
        """Извлечение текста через Tesseract"""
        try:
            if file_path.lower().endswith('.pdf'):
                pages = convert_from_path(file_path, dpi=300, poppler_path=self.poppler_path)
                if not pages:
                    return ""
                pil_image = pages[0]
            else:
                pil_image = Image.open(file_path)

            processed_img = self.preprocess_image(pil_image)

            # Используем несколько языков для лучшего распознавания
            text = pytesseract.image_to_string(
                processed_img,
                lang="kaz+rus+eng",
                config='--psm 6'  # Assume uniform block of text
            )

            if self.debug:
                print("📄 OCR TEXT START" + "="*40)
                print(text)
                print("="*40 + " OCR TEXT END")

            return text
        except Exception as e:
            print(f"❌ Ошибка OCR: {e}")
            return ""

    def get_gender_from_iin(self, iin: str) -> str:
        """Определение пола по 7-й цифре ИИН"""
        if not iin or len(iin) != 12 or not iin.isdigit():
            return ""
        digit = int(iin[6])
        return "M" if digit in [1, 3, 5] else "F" if digit in [2, 4, 6] else ""

    def extract_date_from_iin(self, iin: str) -> str:
        """Извлечение даты рождения из ИИН (первые 6 цифр - YYMMDD)"""
        if not iin or len(iin) < 6 or not iin[:6].isdigit():
            return ""

        try:
            yy = int(iin[0:2])
            mm = int(iin[2:4])
            dd = int(iin[4:6])

            # Определяем век по 7-й цифре
            century_digit = int(iin[6]) if len(iin) > 6 else 0
            if century_digit in [1, 2]:
                year = 1800 + yy
            elif century_digit in [3, 4]:
                year = 1900 + yy
            elif century_digit in [5, 6]:
                year = 2000 + yy
            else:
                year = 1900 + yy  # По умолчанию 1900-е

            # Проверяем валидность даты
            datetime(year, mm, dd)

            return f"{dd:02d}.{mm:02d}.{year}"
        except (ValueError, IndexError):
            return ""

    def parse_mrz(self, text: str) -> dict:
        """Парсинг MRZ (Machine Readable Zone) - строка внизу паспорта"""
        mrz_data = {}
        raw_lines = [line.strip().replace(" ", "") for line in text.splitlines()]
        mrz_lines = [re.sub(r'[^A-Z0-9<]', '', line) for line in raw_lines if len(re.sub(r'[^A-Z0-9<]', '', line)) >= 25]

        if len(mrz_lines) < 2:
            match = re.search(r'([A-Z]{2,})<<([A-Z]{2,})', text)
            if match:
                mrz_data["last_name"] = match.group(1).replace("<", "")
                mrz_data["first_name"] = match.group(2).replace("<", "")
            return mrz_data

        line1, line2 = mrz_lines[-2], mrz_lines[-1]
        if self.debug:
            print(f"✅ MRZ строка 1: {line1}")
            print(f"✅ MRZ строка 2: {line2}")

        if line1.startswith("P<") and len(line1) > 5:
            name_field = line1[5:]
        else:
            name_field = line1
        name_part = name_field.split("<<", 1)
        if name_part:
            mrz_data["last_name"] = name_part[0].replace("<", "")
            if len(name_part) > 1:
                mrz_data["first_name"] = name_part[1].replace("<", " ").strip()

        if len(line2) >= 9:
            mrz_doc = line2[0:9].replace("<", "")
            if mrz_doc:
                mrz_data["document_number"] = mrz_doc

        raw_exp = line2[21:27] if len(line2) >= 27 else ""
        exp_date = self._mrz_date_to_iso(raw_exp)
        if exp_date:
            mrz_data["expiration_date"] = exp_date

        return mrz_data

    def _mrz_date_to_iso(self, raw: str) -> str:
        """Преобразование даты MRZ YYMMDD -> DD.MM.YYYY"""
        if not raw or not raw.isdigit() or len(raw) != 6:
            return ""
        yy = int(raw[0:2])
        mm = int(raw[2:4])
        dd = int(raw[4:6])
        year = 2000 + yy
        current_year = datetime.now().year
        if year < current_year - 20:
            year += 100
        try:
            datetime(year, mm, dd)
            return f"{dd:02d}.{mm:02d}.{year}"
        except ValueError:
            return ""

    def parse_text(self, text: str) -> PassportData:
        """Основной парсинг текста паспорта"""
        data = PassportData()

        if self.debug:
            print("\n" + "="*60)
            print("🔍 НАЧАЛО ПАРСИНГА")
            print("="*60)

        # 1. ИИН (12 цифр подряд)
        iin_match = re.search(r'\b(\d{12})\b', text)
        if iin_match:
            data.iin = iin_match.group(1)
            if self.debug:
                print(f"✅ ИИН: {data.iin}")

            # Извлекаем пол и дату рождения из ИИН
            data.gender = self.get_gender_from_iin(data.iin)
            iin_dob = self.extract_date_from_iin(data.iin)
            if iin_dob and not data.dob:
                data.dob = iin_dob
                if self.debug:
                    print(f"✅ Дата рождения из ИИН: {data.dob}")

        # 2. ПОЛ (если не определен из ИИН)
        if not data.gender:
            # Ищем пол в тексте
            gender_patterns = [
                r'(?:ЖЫНЫСЫ|Sex|Gender)[\s:]*([МЖMFмжmf])',
                r'Sex[\s/]*([MF])',
                r'Gender[\s:]*([MF])',
            ]

            for pattern in gender_patterns:
                gender_match = re.search(pattern, text, re.IGNORECASE)
                if gender_match:
                    g = gender_match.group(1).upper()
                    if g in ['M', 'М']:
                        data.gender = "M"
                    elif g in ['F', 'Ж']:
                        data.gender = "F"
                    if data.gender:
                        if self.debug:
                            print(f"✅ Пол (текст): {data.gender}")
                        break

        # 3. НОМЕР ДОКУМЕНТА (N + 8 цифр)
        doc_patterns = [
            r'(N\d{8})',  # N12345678
            r'№[\s]*([NА-Я0-9]{8,9})',  # № N12345678
            r'ПАСПОРТ[^\n]*?([A-Z0-9]{8,9})',  # После слова ПАСПОРТ
        ]

        for pattern in doc_patterns:
            doc_match = re.search(pattern, text)
            if doc_match:
                data.document_number = doc_match.group(1).strip()
                if self.debug:
                    print(f"✅ Номер документа: {data.document_number}")
                break

        # 4. ФАМИЛИЯ И ИМЯ
        # Сначала пробуем найти через заголовки
        surname_patterns = [
            r'(?:ТЕП\s*/?\s*ЗҰҢАТМЕ|ТЕП|ТЕГІ|Surname)[\s:]*\n+([A-ZА-ЯӘӨҮҰҒҚҢҺІЁA-Z\s]+)',
            r'(?:Last\s*Name)[\s:]*\n+([A-Z\s]+)',
        ]

        for pattern in surname_patterns:
            surname_match = re.search(pattern, text, re.IGNORECASE)
            if surname_match:
                data.last_name = surname_match.group(1).strip()
                if self.debug:
                    print(f"✅ Фамилия: {data.last_name}")
                break

        # Имя
        name_patterns = [
            r'(?:АТЫ|Given\s*name|First\s*Name)[\s:]*\n+([A-ZА-ЯӘӨҮҰҒҚҢҺІЁA-Z\s]+)',
        ]

        for pattern in name_patterns:
            name_match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if name_match:
                name_text = name_match.group(1).strip()
                # Берем только первую строку (может быть и латиница, и кириллица)
                lines = name_text.split('\n')
                for line in lines:
                    clean_line = line.strip()
                    # Проверяем, что это только буквы
                    if clean_line and re.match(r'^[A-ZА-ЯӘӨҮҰҒҚҢҺІЁ\s]+$', clean_line):
                        data.first_name = clean_line
                        if self.debug:
                            print(f"✅ Имя: {data.first_name}")
                        break
                if data.first_name:
                    break

        # 5. ДАТЫ
        # Дата рождения
        if not data.dob:
            dob_patterns = [
                r'(?:ТУҒАН\s*КҮНІ|Date\s*of\s*birth|Дата\s*рождения)[\s:]*(\d{2}[./]\d{2}[./]\d{4})',
                r'(?:Born|Родился)[\s:]*(\d{2}[./]\d{2}[./]\d{4})',
                r'(\d{2}\.\d{2}\.\d{4})',  # Просто формат даты
            ]

            for pattern in dob_patterns:
                dob_match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if dob_match:
                    data.dob = dob_match.group(1).replace('/', '.')
                    if self.debug:
                        print(f"✅ Дата рождения: {data.dob}")
                    break

        # Срок действия
        exp_patterns = [
            r'(?:МЕРЗІМ(?:І)?|ЖАРАМДЫ\s*ДО|Expiry|Expires|Valid\s*(?:until|to)|Date\s*of\s*Expiry|Действителен\s*до)[^\d]*(\d{2}\s*[./-]\s*\d{2}\s*[./-]\s*\d{4})',
            r'(?:Valid\s*until)[\s:]*(\d{2}\s*[./-]\s*\d{2}\s*[./-]\s*\d{4})',
            r'(?:до\s*)(\d{2}\s*[./-]\s*\d{2}\s*[./-]\s*\d{4})',
        ]

        for pattern in exp_patterns:
            exp_match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if exp_match:
                data.expiration_date = self._clean_date(exp_match.group(1))
                if self.debug:
                    print(f"✅ Срок действия: {data.expiration_date}")
                break

        # 6. MRZ OVERRIDE (самый точный источник имен)
        mrz_data = self.parse_mrz(text)
        if mrz_data.get("last_name"):
            data.last_name = mrz_data["last_name"]
            if self.debug:
                print(f"✅ Фамилия (MRZ override): {data.last_name}")
        if mrz_data.get("first_name"):
            data.first_name = mrz_data["first_name"]
            if self.debug:
                print(f"✅ Имя (MRZ override): {data.first_name}")
        if mrz_data.get("document_number") and not data.document_number:
            data.document_number = mrz_data["document_number"]
            if self.debug:
                print(f"✅ Номер документа (MRZ): {data.document_number}")
        if mrz_data.get("expiration_date") and not data.expiration_date:
            data.expiration_date = mrz_data["expiration_date"]
            if self.debug:
                print(f"✅ Срок действия (MRZ): {data.expiration_date}")

        if not data.expiration_date:
            generic_matches = re.findall(r'(\d{2}(?:\s*[./-]\s*|\s+)\d{2}(?:\s*[./-]\s*|\s+)\d{4})', text)
            for match in reversed(generic_matches):
                cleaned = self._clean_date(match)
                if cleaned and cleaned != data.dob:
                    data.expiration_date = cleaned
                    if self.debug:
                        print(f"✅ Срок действия (fallback): {data.expiration_date}")
                    break

        if self.debug:
            print("="*60)
            print(f"📊 ИТОГОВЫЕ ДАННЫЕ:")
            print(f"   Фамилия: {data.last_name}")
            print(f"   Имя: {data.first_name}")
            print(f"   Пол: {data.gender}")
            print(f"   Дата рождения: {data.dob}")
            print(f"   ИИН: {data.iin}")
            print(f"   Документ: {data.document_number}")
            print(f"   Срок действия: {data.expiration_date}")
            print(f"   Валидность: {data.is_valid}")
            print("="*60 + "\n")

        return data

    def parse(self, file_path: str) -> PassportData:
        """Главный метод парсинга файла"""
        text = self.extract_ocr_text(file_path)
        return self.parse_text(text)


# Функция для быстрого тестирования
def test_parser(file_path: str):
    parser = PassportParser(debug=True)
    result = parser.parse(file_path)
    print("\n🎯 РЕЗУЛЬТАТ:")
    print(result.to_dict())
    return result
