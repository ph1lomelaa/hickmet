"""
Парсер паспортов на EasyOCR (уже установлен!)
Работает лучше Tesseract, проще PaddleOCR
"""

import easyocr
from passporteye import read_mrz
from PIL import Image
from pdf2image import convert_from_path
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import os


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
    phone: str = ""
    nationality: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.last_name} {self.first_name}".strip()

    @property
    def is_valid(self) -> bool:
        has_name = bool(self.last_name or self.first_name)
        has_iin = len(self.iin) == 12 if self.iin else False
        has_doc = bool(self.document_number)
        return has_name and (has_iin or has_doc)

    def to_dict(self) -> dict:
        """Возвращает данные в формате для API (совместимость с booking_handlers.py)"""
        return {
            # Snake_case формат (для writer.py и test скриптов)
            "last_name": self.last_name or "-",
            "first_name": self.first_name or "-",
            "gender": self.gender or "M",
            "date_of_birth": self.dob or "-",
            "passport_num": self.document_number or "-",
            "phone": self.phone or "-",
            "nationality": self.nationality or "KAZ",
            "iin": self.iin or "-",
            # Дополнительные поля для совместимости с booking_handlers.py
            "Last Name": self.last_name or "-",
            "First Name": self.first_name or "-",
            "Gender": self.gender or "M",
            "Date of Birth": self.dob or "-",
            "Document Number": self.document_number or "-",
            "Document Expiration": self.expiration_date or "-",
            "IIN": self.iin or "-",
            "MRZ_LAST": getattr(self, "mrz_last_name", None),
            "MRZ_FIRST": getattr(self, "mrz_first_name", None),
        }


class PassportParserEasyOCR:
    """
    Парсер на EasyOCR + PassportEye
    Лучше работает, чем Tesseract
    """

    def __init__(self, poppler_path: str = None, debug: bool = False):
        self.poppler_path = poppler_path
        self.debug = debug

        # Инициализация EasyOCR (английский + русский)
        # Первый запуск скачает модели (~100MB)
        self.reader = easyocr.Reader(['en', 'ru'])

    def validate_iin_checksum(self, iin: str) -> bool:
        """Проверка контрольной суммы ИИН"""
        if not iin or len(iin) != 12 or not iin.isdigit():
            return False
        weights1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        checksum = sum(int(iin[i]) * weights1[i] for i in range(11)) % 11
        if checksum == 10:
            weights2 = [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2]
            checksum = sum(int(iin[i]) * weights2[i] for i in range(11)) % 11
        return checksum == int(iin[11])

    def get_gender_from_iin(self, iin: str) -> str:
        if not iin or len(iin) != 12:
            return ""
        digit = int(iin[6])
        return "M" if digit in [1, 3, 5] else "F" if digit in [2, 4, 6] else ""

    def extract_date_from_iin(self, iin: str) -> str:
        if not iin or len(iin) < 6:
            return ""
        try:
            yy, mm, dd = int(iin[0:2]), int(iin[2:4]), int(iin[4:6])
            century_digit = int(iin[6]) if len(iin) > 6 else 0
            if century_digit in [1, 2]:
                year = 1800 + yy
            elif century_digit in [3, 4]:
                year = 1900 + yy
            elif century_digit in [5, 6]:
                year = 2000 + yy
            else:
                year = 1900 + yy
            datetime(year, mm, dd)
            return f"{dd:02d}.{mm:02d}.{year}"
        except:
            return ""

    def extract_text_easyocr(self, file_path: str) -> str:
        """Извлечение текста с EasyOCR"""
        temp_file = None
        try:
            # Конвертируем PDF в изображение
            if file_path.lower().endswith('.pdf'):
                pages = convert_from_path(file_path, dpi=300, poppler_path=self.poppler_path)
                if not pages:
                    return ""
                temp_img = file_path.replace('.pdf', '_temp.jpg')
                pages[0].save(temp_img, 'JPEG')
                file_path = temp_img
                temp_file = temp_img
            # Конвертируем PNG/другие форматы в JPEG для лучшей совместимости
            elif not file_path.lower().endswith(('.jpg', '.jpeg')):
                img = Image.open(file_path)
                # Конвертируем в RGB если нужно
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                temp_jpg = file_path.rsplit('.', 1)[0] + '_temp_ocr.jpg'
                img.save(temp_jpg, 'JPEG', quality=95)
                file_path = temp_jpg
                temp_file = temp_jpg

            # EasyOCR
            result = self.reader.readtext(file_path)

            # Удаляем временный файл
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)

            # Собираем текст
            text_lines = []
            for (bbox, text, confidence) in result:
                # Понижаем порог для лучшего распознавания
                if confidence > 0.3:
                    text_lines.append(text)

            full_text = "\n".join(text_lines)

            if self.debug:
                print("="*60)
                print("📄 EASYOCR TEXT:")
                print(full_text)
                print("="*60)

            return full_text

        except Exception as e:
            # Очищаем временный файл при ошибке
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            if self.debug:
                print(f"❌ Ошибка EasyOCR: {e}")
            return ""

    def extract_mrz_passporteye(self, file_path: str) -> Optional[dict]:
        """Извлечение MRZ с PassportEye"""
        try:
            if file_path.lower().endswith('.pdf'):
                pages = convert_from_path(file_path, dpi=300, poppler_path=self.poppler_path)
                if not pages:
                    return None
                temp_img = file_path.replace('.pdf', '_temp_mrz.jpg')
                pages[0].save(temp_img, 'JPEG')
                file_path = temp_img

            mrz_data = read_mrz(file_path)

            if '_temp_mrz.jpg' in file_path:
                os.remove(file_path)

            if not mrz_data or not mrz_data.mrz_type:
                return None

            result = {}
            if mrz_data.names:
                result['first_name'] = mrz_data.names
            if mrz_data.surname:
                result['last_name'] = mrz_data.surname
            if mrz_data.number:
                result['document_number'] = mrz_data.number
            if mrz_data.date_of_birth:
                result['dob'] = mrz_data.date_of_birth
            if mrz_data.expiration_date:
                result['expiration_date'] = mrz_data.expiration_date
            if mrz_data.sex:
                result['gender'] = mrz_data.sex
            if mrz_data.nationality:
                result['nationality'] = mrz_data.nationality

            if self.debug:
                print("="*60)
                print("📋 PASSPORTEYE MRZ DATA:")
                print(result)
                print("="*60)

            return result

        except Exception as e:
            if self.debug:
                print(f"⚠️ PassportEye: {e}")
            return None

    def validate_mrz_name(self, name: str, field_name: str = "name") -> bool:
        """
        Проверка качества одного имени/фамилии из MRZ
        Возвращает True если имя валидно, False если это мусор
        """
        if not name:
            return True  # Пустое имя - не критично

        # Проверка 1: Слишком много повторяющихся символов (C, O, E, G, S)
        # "SOOCCOCGCECCCOCG..." - явный мусор
        garbage_chars = name.count('C') + name.count('O') + name.count('E') + name.count('G') + name.count('S')
        if len(name) > 0 and (garbage_chars / len(name)) > 0.5:
            if self.debug:
                print(f"⚠️ MRZ {field_name} отклонено: слишком много мусорных символов ({garbage_chars}/{len(name)})")
            return False

        # Проверка 2: Слишком длинное имя без пробелов (>20 символов)
        # "RAYAKXALTYBAEVNA" - имя+отчество слитно
        clean_name = name.replace(' ', '').replace('<', '')
        if len(clean_name) > 20:
            if self.debug:
                print(f"⚠️ MRZ {field_name} отклонено: слишком длинное ({len(clean_name)} символов)")
            return False

        return True

    def validate_document_number(self, doc_num: str) -> bool:
        """Валидация номера документа - отклоняем мусор вроде <<<<<6<<<"""
        if not doc_num:
            return False

        # Проверка 1: Слишком много символов '<' (мусор из MRZ)
        bracket_count = doc_num.count('<')
        if len(doc_num) > 0 and (bracket_count / len(doc_num)) > 0.5:
            if self.debug:
                print(f"⚠️ Номер документа отклонен: слишком много '<' символов ({bracket_count}/{len(doc_num)})")
            return False

        # Проверка 2: Должен содержать хотя бы несколько цифр или букв
        alphanumeric = sum(c.isalnum() for c in doc_num)
        if alphanumeric < 3:
            if self.debug:
                print(f"⚠️ Номер документа отклонен: слишком мало значимых символов ({alphanumeric})")
            return False

        return True

    def validate_date(self, date_str: str) -> bool:
        """Валидация даты - отклоняем мусор вроде EVA<<K"""
        if not date_str:
            return False

        # Проверка 1: Слишком много символов '<' (мусор из MRZ)
        bracket_count = date_str.count('<')
        if len(date_str) > 0 and (bracket_count / len(date_str)) > 0.3:
            if self.debug:
                print(f"⚠️ Дата отклонена: слишком много '<' символов ({bracket_count}/{len(date_str)})")
            return False

        # Проверка 2: Должна содержать хотя бы несколько цифр
        digit_count = sum(c.isdigit() for c in date_str)
        if digit_count < 4:  # Минимум 4 цифры для даты
            if self.debug:
                print(f"⚠️ Дата отклонена: слишком мало цифр ({digit_count})")
            return False

        # Проверка 3: Не должна содержать много букв
        letter_count = sum(c.isalpha() for c in date_str)
        if letter_count > 2:  # Максимум 2 буквы (например, разделители)
            if self.debug:
                print(f"⚠️ Дата отклонена: слишком много букв ({letter_count})")
            return False

        return True

    def validate_mrz_data(self, mrz_data: dict) -> bool:
        """Проверка качества MRZ данных от PassportEye"""
        if not mrz_data:
            return False

        # Проверяем фамилию
        last_name = mrz_data.get('last_name', '')
        if last_name and not self.validate_mrz_name(last_name, "last_name"):
            return False

        # Проверяем имя
        first_name = mrz_data.get('first_name', '')
        if first_name and not self.validate_mrz_name(first_name, "first_name"):
            return False

        # Проверка даты рождения: должна быть в формате DD.MM.YYYY или близко к нему
        dob = mrz_data.get('dob', '')
        if dob:
            # Сначала проверяем общую валидность даты
            if not self.validate_date(dob):
                return False
            # Дополнительно проверяем формат
            if not re.match(r'\d{2}[./]\d{2}[./]\d{4}', dob):
                # Разрешаем только если это похоже на дату (6 цифр подряд)
                if not re.search(r'\d{6}', dob):
                    return False

        # Проверка срока действия
        exp_date = mrz_data.get('expiration_date', '')
        if exp_date and not self.validate_date(exp_date):
            return False

        # Проверка пола: должен быть M или F
        gender = mrz_data.get('gender', '')
        if gender and gender not in ['M', 'F']:
            return False

        # Проверка номера документа
        doc_num = mrz_data.get('document_number', '')
        if doc_num and not self.validate_document_number(doc_num):
            return False

        return True

    def parse_text_fields(self, text: str) -> PassportData:
        """Парсинг полей из текста"""
        data = PassportData()

        # ИИН (12 цифр)
        iin_match = re.search(r'\b(\d{12})\b', text)
        if iin_match:
            iin = iin_match.group(1)
            if self.validate_iin_checksum(iin):
                data.iin = iin
                data.gender = self.get_gender_from_iin(iin)
                data.dob = self.extract_date_from_iin(iin)

        # Номер документа - ищем N и цифры, или буквы+цифры (узбекские паспорта FA1415473)
        doc_patterns = [
            r'N\s*(\d{8,9})',  # N16210280 (казахские)
            r'№\s*(\d{8,9})',  # № 16210280
            r'\b([A-Z]{2}\d{7})\b',  # FA1415473 (узбекские, киргизские)
        ]
        for pattern in doc_patterns:
            doc_match = re.search(pattern, text, re.IGNORECASE)
            if doc_match:
                doc_num = doc_match.group(1)
                # Если начинается с цифр, добавляем N
                if doc_num[0].isdigit():
                    candidate = "N" + doc_num
                else:
                    candidate = doc_num
                # Валидируем перед сохранением
                if self.validate_document_number(candidate):
                    data.document_number = candidate
                    break

        # Служебные слова, которые нужно игнорировать
        EXCLUDE_WORDS = {
            'TYPI', 'TYPE', 'PASSPORT', 'CODE', 'STATE', 'GIVEN', 'NAMES',
            'GIVENNAMES', 'DATE', 'BIRTH', 'PLACE', 'ISSUE', 'EXPIRY',
            'AUTHORITY', 'MINISTRY', 'INTERNAL', 'AFFAIRS', 'KAZAKHSTAN',
            'КАЗАХСТАН', 'ПАСПОРТ', 'DATEOFBIRTH', 'PLACEOFBIRTH',
            'DATEOFISSUE', 'DATEOFEXPIRY', 'AUHORIY', 'CODEOFSTATE'
        }

        # Фамилия - ищем латиницу после английского слова или перед именем

        # Паттерн 1: Узбекские паспорта (FAMILIYASI/SURNAME, ISMI/GIVEN NAMES)
        uzb_surname = re.search(r'(?:FAMILIYASI|SURNAME)[^\n]*\n\s*([A-Z]+)', text, re.IGNORECASE)
        uzb_firstname = re.search(r'(?:ISMI|GIVEN NAMES)[^\n]*\n\s*([A-Z]+)', text, re.IGNORECASE)
        if uzb_surname and uzb_firstname:
            surname = uzb_surname.group(1)
            firstname = uzb_firstname.group(1)
            if surname not in EXCLUDE_WORDS and firstname not in EXCLUDE_WORDS:
                data.last_name = surname
                data.first_name = firstname

        # Паттерн 2: После MRZ строки (казахские паспорта)
        if not data.last_name:
            mrz_surname = re.search(r'([A-Z]{4,})<+([A-Z]{4,})', text)
            if mrz_surname:
                surname = mrz_surname.group(1)
                firstname = mrz_surname.group(2)
                # Проверяем, что это не мусор
                if surname not in EXCLUDE_WORDS and firstname not in EXCLUDE_WORDS:
                    data.last_name = surname
                    data.first_name = firstname

        # Паттерн 3: Обычный текст
        if not data.last_name:
            lines = text.split('\n')
            for i, line in enumerate(lines):
                # Ищем латинские заглавные слова (фамилия/имя обычно рядом)
                latin_words = re.findall(r'\b([A-Z]{4,})\b', line)
                # Фильтруем служебные слова
                latin_words = [w for w in latin_words if w not in EXCLUDE_WORDS]
                if len(latin_words) >= 2:
                    data.last_name = latin_words[0]
                    data.first_name = latin_words[1]
                    break

        # Дата рождения
        if not data.dob:
            # Формат DD.MM.YYYY
            dob_match = re.search(r'\b(\d{2}\.\d{2}\.\d{4})\b', text)
            if dob_match:
                data.dob = dob_match.group(1)
            else:
                # Формат "DD MM YYYY" (узбекские паспорта)
                dob_match = re.search(r'(?:DATE\s*OF\s*BIRTH|DNEOF\s*BIRTH)[^\d]*(\d{2})\s+(\d{2})\s+(\d{4})', text, re.IGNORECASE)
                if dob_match:
                    dd, mm, yyyy = dob_match.groups()
                    data.dob = f"{dd}.{mm}.{yyyy}"

        # Срок действия - обычно последняя дата
        dates = re.findall(r'\b(\d{2}\.\d{2}\.\d{4})\b', text)
        if len(dates) >= 2:
            data.expiration_date = dates[-1]  # Последняя дата

        # Пол - УСИЛЕННОЕ РАСПОЗНАВАНИЕ (обязательное поле!)
        if not data.gender:
            # Паттерн 1: После SEX/ЖЫНЫСЫ
            gender_match = re.search(r'(?:SEX|ЖЫНЫСЫ)[:\s]*([МЖ/MF])', text, re.IGNORECASE)
            if gender_match:
                g = gender_match.group(1).upper()
                data.gender = "M" if g in ['M', 'М'] else "F" if g in ['F', 'Ж'] else ""

        if not data.gender:
            # Паттерн 2: Одиночная буква M/F/М/Ж на отдельной строке или после пробелов
            gender_match = re.search(r'\b([МЖ]|[MF])\b', text, re.IGNORECASE)
            if gender_match:
                g = gender_match.group(1).upper()
                data.gender = "M" if g in ['M', 'М'] else "F" if g in ['F', 'Ж'] else ""

        if not data.gender:
            # Паттерн 3: Ищем "MALE" или "FEMALE"
            if re.search(r'\bMALE\b', text, re.IGNORECASE):
                data.gender = "M"
            elif re.search(r'\bFEMALE\b', text, re.IGNORECASE):
                data.gender = "F"

        # Национальность
        if not data.nationality:
            # Ищем UZBEKISTAN, KAZAKHSTAN и т.д.
            nationality_match = re.search(r'\b(UZBEKISTAN|KAZAKHSTAN|KYRGYZSTAN|TAJIKISTAN|TURKMENISTAN)\b', text, re.IGNORECASE)
            if nationality_match:
                country = nationality_match.group(1).upper()
                # Конвертируем в код страны
                nationality_map = {
                    'UZBEKISTAN': 'UZB',
                    'KAZAKHSTAN': 'KAZ',
                    'KYRGYZSTAN': 'KGZ',
                    'TAJIKISTAN': 'TJK',
                    'TURKMENISTAN': 'TKM'
                }
                data.nationality = nationality_map.get(country, 'KAZ')

        # Телефон
        phone_match = re.search(r'(?:\+7|8)\s?\(?\d{3}\)?\s?\d{3}[\s-]?\d{2}[\s-]?\d{2}', text)
        if phone_match:
            data.phone = phone_match.group(0)

        return data

    def parse(self, file_path: str) -> PassportData:
        """Главный метод парсинга"""
        if self.debug:
            print(f"\n🔍 Парсинг файла: {file_path}")

        # 1. PassportEye для MRZ
        mrz_data = self.extract_mrz_passporteye(file_path)

        # 2. EasyOCR для текста
        text = self.extract_text_easyocr(file_path)

        # 3. Парсим текст
        data = self.parse_text_fields(text)

        # 4. Сохраняем оригинальные имена из EasyOCR (до применения MRZ)
        easyocr_last_name = data.last_name
        easyocr_first_name = data.first_name

        # 5. MRZ переопределяет (приоритет) - используем выборочно
        if mrz_data:
            # Сохраняем MRZ имена отдельно для booking_handlers.py
            if mrz_data.get('last_name'):
                data.mrz_last_name = mrz_data['last_name']
            if mrz_data.get('first_name'):
                data.mrz_first_name = mrz_data['first_name']

            # Проверяем валидность всех MRZ данных
            mrz_valid = self.validate_mrz_data(mrz_data)

            if mrz_valid:
                # Все MRZ данные валидны - используем все
                if self.debug:
                    print("✅ MRZ данные прошли валидацию, используем их")
                if mrz_data.get('last_name'):
                    data.last_name = mrz_data['last_name']
                if mrz_data.get('first_name'):
                    data.first_name = mrz_data['first_name']
                if mrz_data.get('document_number'):
                    data.document_number = mrz_data['document_number']
                if mrz_data.get('dob'):
                    data.dob = mrz_data['dob']
                if mrz_data.get('expiration_date'):
                    data.expiration_date = mrz_data['expiration_date']
                if mrz_data.get('gender'):
                    data.gender = mrz_data['gender']
                if mrz_data.get('nationality'):
                    data.nationality = mrz_data['nationality']
            else:
                # MRZ не прошла полную валидацию, но берем отдельные валидные поля
                if self.debug:
                    print("⚠️ MRZ данные не прошли полную валидацию, используем выборочно")

                # Документ - берем если пустой в EasyOCR и валиден
                if not data.document_number and mrz_data.get('document_number'):
                    mrz_doc = mrz_data['document_number']
                    if self.validate_document_number(mrz_doc):
                        data.document_number = mrz_doc

                # Дата рождения - берем если пустая в EasyOCR и валидна
                if not data.dob and mrz_data.get('dob'):
                    mrz_dob = mrz_data['dob']
                    # Проверяем валидность и формат
                    if self.validate_date(mrz_dob) and re.match(r'\d{6}', mrz_dob):
                        data.dob = mrz_dob

                # Пол - берем если пустой в EasyOCR и валиден (M или F)
                if not data.gender and mrz_data.get('gender') in ['M', 'F']:
                    data.gender = mrz_data['gender']

                # Национальность - берем если пустая в EasyOCR
                if not data.nationality and mrz_data.get('nationality'):
                    data.nationality = mrz_data['nationality']

                # Срок действия - берем если пустой и валиден
                if not data.expiration_date and mrz_data.get('expiration_date'):
                    mrz_exp = mrz_data['expiration_date']
                    if self.validate_date(mrz_exp):
                        data.expiration_date = mrz_exp

        # 6. ГИБКАЯ ПРИОРИТИЗАЦИЯ: если EasyOCR нашел четкое короткое имя,
        # а MRZ содержит длинное (имя+отчество слитно), используем EasyOCR
        if easyocr_first_name and data.first_name:
            # Если EasyOCR имя существенно короче MRZ имени (>5 символов разница)
            # И EasyOCR имя не слишком короткое (>2 символов)
            if len(easyocr_first_name) > 2 and len(data.first_name) - len(easyocr_first_name) > 5:
                if self.debug:
                    print(f"🔄 Приоритизируем EasyOCR имя '{easyocr_first_name}' вместо MRZ '{data.first_name}'")
                data.first_name = easyocr_first_name

        if easyocr_last_name and data.last_name:
            # То же самое для фамилии
            if len(easyocr_last_name) > 2 and len(data.last_name) - len(easyocr_last_name) > 5:
                if self.debug:
                    print(f"🔄 Приоритизируем EasyOCR фамилию '{easyocr_last_name}' вместо MRZ '{data.last_name}'")
                data.last_name = easyocr_last_name

        # 7. ФИНАЛЬНАЯ ПРОВЕРКА ПОЛА - обязательное поле!
        if not data.gender:
            # Fallback: пытаемся определить по имени (распространенные имена)
            if data.first_name:
                name_lower = data.first_name.lower()
                # Женские окончания
                female_endings = ['a', 'ya', 'ia', 'na', 'ra', 'la', 'ma', 'ta', 'sa']
                # Распространенные женские имена
                female_names = {'aisha', 'aiman', 'ainur', 'aiya', 'akmaral', 'aliya', 'alma', 'altynai',
                                'anar', 'asem', 'asiya', 'aygerim', 'aynur', 'azhar', 'diana', 'dinara',
                                'farida', 'fatima', 'gaukhar', 'gulnara', 'gulzhan', 'indira', 'kamila',
                                'karlygash', 'karina', 'kulyaim', 'laura', 'madina', 'malika', 'mariam',
                                'nazira', 'raya', 'saule', 'symbat', 'togzhan', 'ulzhan', 'zarina', 'zhanna'}

                # Проверяем по окончанию
                if any(name_lower.endswith(ending) for ending in female_endings):
                    data.gender = "F"
                    if self.debug:
                        print(f"🔄 Пол определен по окончанию имени '{data.first_name}': F")
                # Проверяем по списку известных женских имен
                elif name_lower in female_names:
                    data.gender = "F"
                    if self.debug:
                        print(f"🔄 Пол определен по базе имен '{data.first_name}': F")
                else:
                    # По умолчанию - мужской
                    data.gender = "M"
                    if self.debug:
                        print(f"⚠️ Пол не распознан, используем по умолчанию: M")
            else:
                # Совсем нет данных - по умолчанию мужской
                data.gender = "M"
                if self.debug:
                    print(f"⚠️ Пол не распознан (нет имени), используем по умолчанию: M")

        # 8. Валидация номера документа - отклоняем мусор
        if data.document_number and not self.validate_document_number(data.document_number):
            if self.debug:
                print(f"❌ Номер документа '{data.document_number}' не прошел валидацию, сбрасываем")
            data.document_number = ""

        # 9. Валидация даты рождения - отклоняем мусор
        if data.dob and not self.validate_date(data.dob):
            if self.debug:
                print(f"❌ Дата рождения '{data.dob}' не прошла валидацию, сбрасываем")
            data.dob = ""

        # 10. Валидация срока действия - отклоняем мусор вроде EVA<<K
        if data.expiration_date and not self.validate_date(data.expiration_date):
            if self.debug:
                print(f"❌ Срок действия '{data.expiration_date}' не прошел валидацию, сбрасываем")
            data.expiration_date = ""

        if self.debug:
            print("\n📊 ИТОГОВЫЕ ДАННЫЕ:")
            print(f"   Фамилия: {data.last_name}")
            print(f"   Имя: {data.first_name}")
            print(f"   Документ: {data.document_number}")
            print(f"   ИИН: {data.iin}")
            print(f"   Дата рождения: {data.dob}")
            print(f"   Пол: {data.gender}")
            print(f"   Валидность: {data.is_valid}")
            print("="*60)

        return data


def test_easyocr_parser(file_path: str):
    """Тестирование парсера"""
    parser = PassportParserEasyOCR(debug=True)
    result = parser.parse(file_path)
    print("\n🎯 РЕЗУЛЬТАТ:")
    print(result.to_dict())
    return result
