import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import easyocr
from passporteye import read_mrz
from pdf2image import convert_from_path
from PIL import Image


@dataclass
class PassportDataEasyOCR:
    """Данные паспорта (совместимо с booking_handlers.py)."""
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
        return {
            "last_name": self.last_name or "-",
            "first_name": self.first_name or "-",
            "gender": self.gender or "M",
            "date_of_birth": self.dob or "-",
            "passport_num": self.document_number or "-",
            "phone": self.phone or "-",
            "nationality": self.nationality or "KAZ",
            "iin": self.iin or "-",
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
    """Парсер на EasyOCR + PassportEye (альтернатива Tesseract)."""

    def __init__(self, poppler_path: str = None, debug: bool = False):
        self.poppler_path = poppler_path
        self.debug = debug
        self.reader = easyocr.Reader(["en", "ru"])

    # ----------------- Утилиты -----------------
    def validate_iin_checksum(self, iin: str) -> bool:
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
        except Exception:
            return ""

    # ----------------- OCR -----------------
    def extract_text_easyocr(self, file_path: str) -> str:
        temp_file = None
        try:
            if file_path.lower().endswith(".pdf"):
                pages = convert_from_path(file_path, dpi=300, poppler_path=self.poppler_path)
                if not pages:
                    return ""
                temp_img = file_path.replace(".pdf", "_temp.jpg")
                pages[0].save(temp_img, "JPEG")
                file_path = temp_img
                temp_file = temp_img
            elif not file_path.lower().endswith((".jpg", ".jpeg")):
                img = Image.open(file_path)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                temp_jpg = file_path.rsplit(".", 1)[0] + "_temp_ocr.jpg"
                img.save(temp_jpg, "JPEG", quality=95)
                file_path = temp_jpg
                temp_file = temp_jpg

            result = self.reader.readtext(file_path)

            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)

            text_lines = [text for (_, text, conf) in result if conf > 0.3]
            full_text = "\n".join(text_lines)

            if self.debug:
                print("=" * 60)
                print("📄 EASYOCR TEXT:")
                print(full_text)
                print("=" * 60)

            return full_text
        except Exception as e:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
            if self.debug:
                print(f"❌ Ошибка EasyOCR: {e}")
            return ""

    def extract_mrz_passporteye(self, file_path: str) -> Optional[dict]:
        try:
            temp_path = None
            if file_path.lower().endswith(".pdf"):
                pages = convert_from_path(file_path, dpi=300, poppler_path=self.poppler_path)
                if not pages:
                    return None
                temp_img = file_path.replace(".pdf", "_temp_mrz.jpg")
                pages[0].save(temp_img, "JPEG")
                file_path = temp_img
                temp_path = temp_img

            mrz_data = read_mrz(file_path)

            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

            if not mrz_data or not mrz_data.mrz_type:
                return None

            result = {}
            if mrz_data.names:
                result["first_name"] = mrz_data.names
            if mrz_data.surname:
                result["last_name"] = mrz_data.surname
            if mrz_data.number:
                result["document_number"] = mrz_data.number
            if mrz_data.date_of_birth:
                result["dob"] = mrz_data.date_of_birth
            if mrz_data.expiration_date:
                result["expiration_date"] = mrz_data.expiration_date
            if mrz_data.sex:
                result["gender"] = mrz_data.sex
            if mrz_data.nationality:
                result["nationality"] = mrz_data.nationality

            if self.debug:
                print("=" * 60)
                print("📋 PASSPORTEYE MRZ DATA:")
                print(result)
                print("=" * 60)

            return result
        except Exception as e:
            if self.debug:
                print(f"⚠️ PassportEye: {e}")
            return None

    # ----------------- Валидации -----------------
    def validate_mrz_name(self, name: str, field_name: str = "name") -> bool:
        if not name:
            return True
        garbage = name.count("C") + name.count("O") + name.count("E") + name.count("G") + name.count("S")
        if len(name) > 0 and (garbage / len(name)) > 0.5:
            if self.debug:
                print(f"⚠️ MRZ {field_name} отклонено: мусор {garbage}/{len(name)}")
            return False
        clean = name.replace(" ", "").replace("<", "")
        if len(clean) > 20:
            if self.debug:
                print(f"⚠️ MRZ {field_name} отклонено: слишком длинно ({len(clean)})")
            return False
        return True

    def validate_document_number(self, doc_num: str) -> bool:
        if not doc_num:
            return False
        if len(doc_num) > 0 and (doc_num.count("<") / len(doc_num)) > 0.5:
            return False
        alnum = sum(c.isalnum() for c in doc_num)
        return alnum >= 3

    def validate_date(self, date_str: str) -> bool:
        if not date_str:
            return False
        if len(date_str) > 0 and (date_str.count("<") / len(date_str)) > 0.3:
            return False
        if sum(c.isdigit() for c in date_str) < 4:
            return False
        if sum(c.isalpha() for c in date_str) > 2:
            return False
        return True

    def validate_mrz_data(self, mrz_data: dict) -> bool:
        if not mrz_data:
            return False
        last_name = mrz_data.get("last_name", "")
        first_name = mrz_data.get("first_name", "")
        if last_name and not self.validate_mrz_name(last_name, "last_name"):
            return False
        if first_name and not self.validate_mrz_name(first_name, "first_name"):
            return False
        dob = mrz_data.get("dob", "")
        if dob and (not self.validate_date(dob) or not re.match(r"\d{6}", dob)):
            return False
        exp = mrz_data.get("expiration_date", "")
        if exp and not self.validate_date(exp):
            return False
        gender = mrz_data.get("gender", "")
        if gender and gender not in ["M", "F"]:
            return False
        doc_num = mrz_data.get("document_number", "")
        if doc_num and not self.validate_document_number(doc_num):
            return False
        return True

    # ----------------- Парсинг текста -----------------
    def parse_text_fields(self, text: str) -> PassportDataEasyOCR:
        data = PassportDataEasyOCR()

        iin_match = re.search(r"\b(\d{12})\b", text)
        if iin_match:
            iin = iin_match.group(1)
            if self.validate_iin_checksum(iin):
                data.iin = iin
                data.gender = self.get_gender_from_iin(iin)
                data.dob = self.extract_date_from_iin(iin)

        doc_patterns = [r"N\s*(\d{8,9})", r"№\s*(\d{8,9})", r"\b([A-Z]{2}\d{7})\b"]
        for pattern in doc_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                raw = m.group(1)
                candidate = "N" + raw if raw[0].isdigit() else raw
                if self.validate_document_number(candidate):
                    data.document_number = candidate
                    break

        EXCLUDE = {
            "TYPE",
            "PASSPORT",
            "CODE",
            "STATE",
            "GIVEN",
            "NAMES",
            "DATE",
            "BIRTH",
            "PLACE",
            "ISSUE",
            "EXPIRY",
            "AUTHORITY",
            "MINISTRY",
            "INTERNAL",
            "AFFAIRS",
            "KAZAKHSTAN",
            "КАЗАХСТАН",
        }

        if not data.last_name:
            mrz_surname = re.search(r"([A-Z]{4,})<+([A-Z]{2,})", text)
            if mrz_surname:
                s, f = mrz_surname.group(1), mrz_surname.group(2)
                if s not in EXCLUDE and f not in EXCLUDE:
                    data.last_name, data.first_name = s, f

        if not data.last_name:
            for line in text.splitlines():
                words = [w for w in re.findall(r"\b([A-Z]{3,})\b", line) if w not in EXCLUDE]
                if len(words) >= 2:
                    data.last_name, data.first_name = words[0], words[1]
                    break

        if not data.dob:
            m = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", text)
            if m:
                data.dob = m.group(1)

        dates = re.findall(r"\b(\d{2}\.\d{2}\.\d{4})\b", text)
        if len(dates) >= 2:
            data.expiration_date = dates[-1]

        if not data.gender:
            g = re.search(r"(?:SEX|ЖЫНЫСЫ)[:\s]*([МЖMF])", text, re.IGNORECASE)
            if g:
                gv = g.group(1).upper()
                data.gender = "M" if gv in ["M", "М"] else "F"

        if not data.gender:
            g = re.search(r"\b([МЖMF])\b", text, re.IGNORECASE)
            if g:
                gv = g.group(1).upper()
                data.gender = "M" if gv in ["M", "М"] else "F"

        if not data.nationality:
            country = re.search(
                r"\b(UZBEKISTAN|KAZAKHSTAN|KYRGYZSTAN|TAJIKISTAN|TURKMENISTAN)\b",
                text,
                re.IGNORECASE,
            )
            if country:
                cmap = {"UZBEKISTAN": "UZB", "KAZAKHSTAN": "KAZ", "KYRGYZSTAN": "KGZ", "TAJIKISTAN": "TJK", "TURKMENISTAN": "TKM"}
                data.nationality = cmap.get(country.group(1).upper(), "KAZ")

        phone = re.search(r"(?:\+7|8)\s?\(?\d{3}\)?\s?\d{3}[\s-]?\d{2}[\s-]?\d{2}", text)
        if phone:
            data.phone = phone.group(0)

        return data

    # ----------------- Главный метод -----------------
    def parse(self, file_path: str) -> PassportDataEasyOCR:
        if self.debug:
            print(f"\n🔍 Парсинг файла (EasyOCR): {file_path}")

        mrz_data = self.extract_mrz_passporteye(file_path)
        text = self.extract_text_easyocr(file_path)
        data = self.parse_text_fields(text)

        easy_last, easy_first = data.last_name, data.first_name

        if mrz_data:
            if mrz_data.get("last_name"):
                data.mrz_last_name = mrz_data["last_name"]
            if mrz_data.get("first_name"):
                data.mrz_first_name = mrz_data["first_name"]

            if self.validate_mrz_data(mrz_data):
                if mrz_data.get("last_name"):
                    data.last_name = mrz_data["last_name"]
                if mrz_data.get("first_name"):
                    data.first_name = mrz_data["first_name"]
                if mrz_data.get("document_number"):
                    data.document_number = mrz_data["document_number"]
                if mrz_data.get("dob"):
                    data.dob = mrz_data["dob"]
                if mrz_data.get("expiration_date"):
                    data.expiration_date = mrz_data["expiration_date"]
                if mrz_data.get("gender"):
                    data.gender = mrz_data["gender"]
                if mrz_data.get("nationality"):
                    data.nationality = mrz_data["nationality"]
            else:
                if not data.document_number and mrz_data.get("document_number"):
                    mrz_doc = mrz_data["document_number"]
                    if self.validate_document_number(mrz_doc):
                        data.document_number = mrz_doc
                if not data.dob and mrz_data.get("dob"):
                    mrz_dob = mrz_data["dob"]
                    if self.validate_date(mrz_dob) and re.match(r"\d{6}", mrz_dob):
                        data.dob = mrz_dob
                if not data.gender and mrz_data.get("gender") in ["M", "F"]:
                    data.gender = mrz_data["gender"]
                if not data.nationality and mrz_data.get("nationality"):
                    data.nationality = mrz_data["nationality"]
                if not data.expiration_date and mrz_data.get("expiration_date"):
                    mrz_exp = mrz_data["expiration_date"]
                    if self.validate_date(mrz_exp):
                        data.expiration_date = mrz_exp

        if easy_first and data.first_name and len(data.first_name) - len(easy_first) > 5 and len(easy_first) > 2:
            data.first_name = easy_first
        if easy_last and data.last_name and len(data.last_name) - len(easy_last) > 5 and len(easy_last) > 2:
            data.last_name = easy_last

        if not data.gender:
            if data.first_name:
                name_lower = data.first_name.lower()
                female_endings = ["a", "ya", "ia", "na", "ra", "la", "ma", "ta", "sa"]
                female_names = {"aisha", "aimur", "ainur", "aiya", "akmaral", "aliya", "alma", "altynai", "anar", "asem", "asiya", "aygerim", "aynur", "azhar", "diana", "dinara", "farida", "fatima", "gaukhar", "gulnara", "gulzhan", "indira", "kamila", "karlygash", "karina", "kulyaim", "laura", "madina", "malika", "mariam", "nazira", "raya", "saule", "symbat", "togzhan", "ulzhan", "zarina", "zhanna"}
                if any(name_lower.endswith(ending) for ending in female_endings) or name_lower in female_names:
                    data.gender = "F"
                else:
                    data.gender = "M"
            else:
                data.gender = "M"

        if data.document_number and not self.validate_document_number(data.document_number):
            data.document_number = ""
        if data.dob and not self.validate_date(data.dob):
            data.dob = ""
        if data.expiration_date and not self.validate_date(data.expiration_date):
            data.expiration_date = ""

        if self.debug:
            print("\n📊 Итоговые данные (EasyOCR):")
            print(data.to_dict())

        return data


def test_easyocr_parser(file_path: str):
    parser = PassportParserEasyOCR(debug=True)
    result = parser.parse(file_path)
    print("\n🎯 РЕЗУЛЬТАТ:")
    print(result.to_dict())
    return result
