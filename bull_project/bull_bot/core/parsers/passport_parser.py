import cv2
import pytesseract
import numpy as np
from pdf2image import convert_from_path
from PIL import Image
import os
import re
from dataclasses import dataclass
from datetime import datetime
import pdfplumber

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
            "MRZ_LAST": getattr(self, "mrz_last_name", None),
            "MRZ_FIRST": getattr(self, "mrz_first_name", None),
        }

class PassportParser:
    def __init__(self, poppler_path: str = None, debug: bool = False, save_ocr: bool = False):
        self.poppler_path = poppler_path
        self.debug = debug
        self.save_ocr = save_ocr  # Новая опция для сохранения OCR текста
        self._date_cleaner = re.compile(r"\s+")
        self._digit_map = {"0": "O", "1": "I", "2": "Z", "3": "Z", "4": "A", "5": "S", "6": "G", "7": "T", "8": "B", "9": "P"}
        self._cyr_map = {
            "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
            "Ж": "ZH", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
            "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
            "Ф": "F", "Х": "KH", "Ц": "TS", "Ч": "CH", "Ш": "SH", "Щ": "SCH",
            "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "YU", "Я": "YA",
            "Қ": "K", "Ә": "A", "Ң": "N", "Ғ": "G", "Ү": "U", "Ұ": "U", "Ө": "O", "Һ": "H", "І": "I", "і": "I",
            "а": "A", "б": "B", "в": "V", "г": "G", "д": "D", "е": "E", "ё": "E",
            "ж": "ZH", "з": "Z", "и": "I", "й": "Y", "к": "K", "л": "L", "м": "M",
            "н": "N", "о": "O", "п": "P", "р": "R", "с": "S", "т": "T", "у": "U",
            "ф": "F", "х": "KH", "ц": "TS", "ч": "CH", "ш": "SH", "щ": "SCH",
            "ъ": "", "ы": "Y", "ь": "", "э": "E", "ю": "YU", "я": "YA",
            "қ": "K", "ә": "A", "ң": "N", "ғ": "G", "ү": "U", "ұ": "U", "ө": "O", "һ": "H",
        }

    def validate_iin_checksum(self, iin: str) -> bool:
        """Проверка контрольной суммы ИИН Казахстана."""
        if not iin or len(iin) != 12 or not iin.isdigit():
            return False

        weights1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        checksum = sum(int(iin[i]) * weights1[i] for i in range(11)) % 11

        if checksum == 10:
            weights2 = [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2]
            checksum = sum(int(iin[i]) * weights2[i] for i in range(11)) % 11

        return checksum == int(iin[11])

    def _calculate_mrz_check_digit(self, data: str) -> int:
        """Расчет контрольной цифры MRZ (стандарт ICAO)."""
        weights = [7, 3, 1]
        total = 0
        for i, char in enumerate(data):
            if char == '<':
                val = 0
            elif '0' <= char <= '9':
                val = ord(char) - ord('0')
            elif 'A' <= char <= 'Z':
                val = ord(char) - ord('A') + 10
            else:
                val = 0
            total += val * weights[i % 3]
        return total % 10

    def _clean_date(self, value: str) -> str:
        """Удаляет лишние пробелы и нормализует разделители."""
        if not value:
            return ""
        stripped = self._date_cleaner.sub("", value)
        stripped = stripped.replace('/', '.').replace('-', '.')
        if len(stripped) == 8 and stripped.isdigit():
            return f"{stripped[0:2]}.{stripped[2:4]}.{stripped[4:]}"
        return stripped

    def _contains_cyrillic(self, value: str) -> bool:
        return any("А" <= c <= "я" or c in "ЁёҚқӘәҢңҒғҮүҰұӨөҺһ" for c in value or "")

    def _transliterate(self, value: str) -> str:
        if not value:
            return ""
        return "".join(self._cyr_map.get(ch, ch) for ch in value)

    def _normalize_token(self, value: str) -> str:
        """
        Приводит имя/фамилию к латинице, убирает шум и OCR-цифры.
        """
        if not value:
            return ""
        # Транслитерация кириллицы
        value = self._transliterate(value)
        # Заменяем похожие цифры на буквы
        value = "".join(self._digit_map.get(ch, ch) for ch in value)
        # Оставляем только латиницу и пробелы
        value = re.sub(r"[^A-Z\s]", "", value.upper())
        return value.strip()

    def preprocess_image(self, image: Image.Image, aggressive: bool = False) -> np.ndarray:
        """Улучшение качества изображения

        Args:
            image: Исходное изображение
            aggressive: Если True, применяет более агрессивную обработку для MRZ
        """
        img = np.array(image)

        # Конвертируем в grayscale если нужно
        if len(img.shape) == 3:
            if img.shape[2] == 4:  # RGBA
                gray = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
            elif img.shape[2] == 3:  # RGB или BGR
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            else:
                gray = img
        elif len(img.shape) == 2:
            # Уже grayscale
            gray = img
        else:
            gray = img

        if aggressive:
            # Агрессивная обработка для MRZ
            # Увеличиваем резкость
            kernel_sharpen = np.array([[-1,-1,-1],
                                      [-1, 9,-1],
                                      [-1,-1,-1]])
            gray = cv2.filter2D(gray, -1, kernel_sharpen)

            # Более сильный CLAHE
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
            enhanced = clahe.apply(gray)

            # Морфологические операции для очистки шума
            kernel = np.ones((2, 2), np.uint8)
            enhanced = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, kernel)

            # Адаптивная бинаризация
            binary = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                          cv2.THRESH_BINARY, 11, 2)
        else:
            # Стандартная обработка
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return binary

    def extract_mrz_from_image(self, pil_image: Image.Image) -> str:
        """Специальное извлечение MRZ зоны с оптимизированным OCR

        Args:
            pil_image: PIL изображение паспорта

        Returns:
            Текст MRZ или пустая строка
        """
        try:
            # Конвертируем в numpy
            img = np.array(pil_image)

            # Если это RGB/RGBA, конвертируем в grayscale сначала
            if len(img.shape) == 3:
                if img.shape[2] == 4:  # RGBA
                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
                elif img.shape[2] == 3:  # RGB
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

            height, width = img.shape[:2]

            # Вырезаем нижние 20% изображения (где обычно находится MRZ)
            # Увеличил с 15% до 20% для большей надежности
            mrz_region = img[int(height * 0.80):, :]

            if self.debug:
                print(f"🔍 MRZ регион: {mrz_region.shape}, диапазон: {int(height * 0.80)} - {height}")

            # Конвертируем обратно в PIL для предобработки
            mrz_pil = Image.fromarray(mrz_region)

            # Попробуем несколько вариантов обработки
            processed_variants = []

            # 1. Стандартная предобработка
            try:
                processed_variants.append(self.preprocess_image(mrz_pil, aggressive=False))
            except:
                pass

            # 2. Агрессивная предобработка
            try:
                processed_variants.append(self.preprocess_image(mrz_pil, aggressive=True))
            except:
                pass

            # 3. Без предобработки (только grayscale)
            try:
                processed_variants.append(mrz_region)
            except:
                pass

            # Попробуем разные комбинации: обработка + конфигурация OCR
            configs = [
                '--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<',  # Стандартная
                '--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<',  # Одна строка
                '--psm 6',  # Без whitelist
            ]

            best_text = ""
            for processed_img in processed_variants:
                for config in configs:
                    try:
                        mrz_text = pytesseract.image_to_string(
                            processed_img,
                            lang="eng",  # Только английский!
                            config=config
                        )
                        # Выбираем результат с наибольшим количеством шевронов или латинских букв
                        score = mrz_text.count('<') * 2 + sum(1 for c in mrz_text if c.isalpha() and c.isupper())
                        best_score = best_text.count('<') * 2 + sum(1 for c in best_text if c.isalpha() and c.isupper())
                        if score > best_score:
                            best_text = mrz_text
                    except:
                        continue

            if self.debug:
                print(f"🔍 MRZ OCR (специальный):")
                print(best_text[:300] if len(best_text) > 300 else best_text)

            return best_text

        except Exception as e:
            if self.debug:
                print(f"⚠️ Ошибка при извлечении MRZ: {e}")
            import traceback
            traceback.print_exc()
            return ""

    def _is_ocr_quality_good(self, text: str) -> bool:
        """Проверяет качество OCR текста - есть ли в нем хоть что-то осмысленное"""
        if not text or len(text) < 20:
            return False

        # Считаем количество букв (латиница + кириллица)
        letters = sum(1 for c in text if c.isalpha())
        # Считаем количество мусора (не буквы, не цифры, не пробелы, не знаки препинания)
        total_chars = len(text.replace(" ", "").replace("\n", ""))

        if total_chars == 0:
            return False

        # Если меньше 40% текста - буквы, это мусор
        letter_ratio = letters / total_chars
        if letter_ratio < 0.4:
            return False

        # Ищем нормальные слова (минимум 4 буквы подряд)
        words = re.findall(r'[A-ZА-ЯӘӨҮҰҒҚҢҺІЁ]{4,}', text, re.IGNORECASE)
        if len(words) < 3:  # Минимум 3 слова
            return False

        # Проверка на явный мусор: слишком много одиночных букв и цифр
        single_chars = re.findall(r'\b[A-ZА-ЯӘӨҮҰҒҚҢҺІЁ0-9]\b', text, re.IGNORECASE)
        if len(single_chars) > len(words) * 2:  # Если одиночных символов больше чем в 2 раза
            return False

        # Дополнительная проверка: ищем ключевые слова паспорта
        # Хороший OCR должен распознать хотя бы одно из этих слов
        passport_keywords = [
            'PASSPORT', 'ПАСПОРТ', 'SURNAME', 'ФАМИЛИЯ', 'NAME', 'ИМЯ',
            'NATIONALITY', 'KAZAKHSTAN', 'КАЗАХСТАН', 'DATE', 'BIRTH'
        ]
        found_keywords = sum(1 for kw in passport_keywords if kw in text.upper())

        # Если нашли меньше 2 ключевых слов - скорее всего мусор
        if found_keywords < 2:
            return False

        return True

    def extract_ocr_text(self, file_path: str) -> tuple:
        """Извлечение текста через Tesseract с fallback на pdfplumber

        Returns:
            tuple: (основной текст, MRZ текст из специального OCR)
        """
        try:
            if file_path.lower().endswith('.pdf'):
                pages = convert_from_path(file_path, dpi=300, poppler_path=self.poppler_path)
                if not pages:
                    return "", ""
                pil_image = pages[0]
            else:
                pil_image = Image.open(file_path)

            # 1. Стандартный OCR для всего документа
            processed_img = self.preprocess_image(pil_image)

            # Используем несколько языков для лучшего распознавания
            text = pytesseract.image_to_string(
                processed_img,
                lang="kaz+rus+eng",
                config='--psm 6'  # Assume uniform block of text
            )

            # Всегда сохраняем OCR текст в файл для отладки
            if self.save_ocr or self.debug:
                ocr_file = file_path + ".ocr_text.txt"
                with open(ocr_file, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"💾 OCR текст сохранен: {ocr_file}")

            if self.debug:
                print("📄 OCR TEXT START" + "="*40)
                print(text)
                print("="*40 + " OCR TEXT END")

            # 2. Специальный OCR для MRZ зоны (только латиница)
            mrz_text = self.extract_mrz_from_image(pil_image)

            # 3. FALLBACK: Если OCR дал плохой результат и это PDF - пробуем pdfplumber
            if not self._is_ocr_quality_good(text) and file_path.lower().endswith('.pdf'):
                if self.debug:
                    print("⚠️ OCR дал плохой результат, пробуем извлечь текст напрямую из PDF...")

                try:
                    with pdfplumber.open(file_path) as pdf:
                        if pdf.pages:
                            pdf_text = pdf.pages[0].extract_text()
                            if pdf_text and len(pdf_text) > len(text):
                                if self.debug:
                                    print("✅ PDF текст извлечен успешно, используем его вместо OCR")
                                    print("📄 PDF TEXT START" + "="*40)
                                    print(pdf_text)
                                    print("="*40 + " PDF TEXT END")
                                text = pdf_text
                                # Для PDF текста не нужен специальный MRZ OCR, он уже есть в тексте
                except Exception as e:
                    if self.debug:
                        print(f"⚠️ Не удалось извлечь текст из PDF: {e}")

            return text, mrz_text
        except Exception as e:
            print(f"❌ Ошибка OCR: {e}")
            return "", ""

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

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Вычисляет расстояние Левенштейна между двумя строками"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def _are_similar_words(self, word1: str, word2: str) -> bool:
        """Проверяет, похожи ли два слова (возможно один вариант - ошибка OCR)"""
        if not word1 or not word2:
            return False

        w1, w2 = word1.upper(), word2.upper()
        if w1 == w2:
            return True

        # Слова должны быть примерно одной длины
        if abs(len(w1) - len(w2)) > 3:
            return False

        # Вычисляем расстояние Левенштейна
        distance = self._levenshtein_distance(w1, w2)
        max_len = max(len(w1), len(w2))

        # Если слова похожи на 60% и более - считаем дубликатами
        similarity = 1 - (distance / max_len)
        if similarity >= 0.6:
            return True

        # Дополнительная проверка: начинаются похоже и заканчиваются похоже
        if len(w1) >= 4 and len(w2) >= 4:
            # Проверяем, что хотя бы 3 из первых 4 букв совпадают
            matches = sum(1 for i in range(min(4, len(w1), len(w2))) if i < len(w1) and i < len(w2) and w1[i] == w2[i])
            if matches >= 3:
                return True

        return False

    def _remove_similar_duplicates(self, parts: list) -> list:
        """Удаляет похожие дубликаты из списка слов (оставляет более правильный вариант)"""
        if len(parts) <= 1:
            return parts

        cleaned = []
        skip_indices = set()

        for i, word in enumerate(parts):
            if i in skip_indices:
                continue

            # Проверяем, есть ли похожее слово дальше
            found_similar = False
            for j in range(i + 1, len(parts)):
                if j in skip_indices:
                    continue

                if self._are_similar_words(word, parts[j]):
                    # Нашли похожее слово - выбираем лучшее
                    # Критерий: слово с большим количеством заглавных латинских букв
                    word_latin_count = sum(1 for c in word if c.isupper() and c.isalpha() and ord('A') <= ord(c) <= ord('Z'))
                    other_latin_count = sum(1 for c in parts[j] if c.isupper() and c.isalpha() and ord('A') <= ord(c) <= ord('Z'))

                    if other_latin_count > word_latin_count:
                        # Другое слово лучше - пропускаем текущее
                        skip_indices.add(i)
                        found_similar = True
                        break
                    else:
                        # Текущее слово лучше - пропускаем другое
                        skip_indices.add(j)

            if not found_similar:
                cleaned.append(word)

        return cleaned

    def _smart_name_split(self, name_string: str) -> tuple:
        """Умное разделение полного имени на фамилию и имя"""
        if not name_string:
            return ("", "")

        # Убираем лишние пробелы и разбиваем
        parts = name_string.strip().split()

        if len(parts) == 0:
            return ("", "")

        # Удаляем похожие дубликаты (OCR часто видит одно слово дважды)
        parts = self._remove_similar_duplicates(parts)

        if len(parts) == 0:
            return ("", "")
        elif len(parts) == 1:
            # Если только одно слово - считаем фамилией
            return (parts[0], "")
        else:
            # Первое слово - фамилия, остальные - имя
            last_name = parts[0]
            first_name = " ".join(parts[1:])
            return (last_name, first_name)

    def _name_quality(self, value: str) -> float:
        """
        Оцениваем качество имени/фамилии: штрафуем короткие обрезки и слишком много токенов.
        Нужно, чтобы MRZ мог перекрыть шумный текст вроде "A Z AF OO".
        """
        if not value:
            return 0.0
        tokens = [t for t in value.split() if t]
        if not tokens:
            return 0.0

        score = sum(len(t) for t in tokens)
        short_tokens = sum(1 for t in tokens if len(t) <= 2)
        score -= short_tokens * 1.5
        if len(tokens) > 2:
            score -= (len(tokens) - 2) * 0.5
        if not all(t.isalpha() for t in tokens):
            score -= 1

        return score

    def _remove_noise_tokens(self, value: str) -> str:
        """Убираем служебные слова, попавшие в итоговые имена."""
        if not value:
            return ""
        noise = {
            "SURNAME", "GIVEN", "NAMES", "GIVENNAMES", "FIRST", "NAME",
            "DATE", "OF", "BIRTH",
        }
        tokens = [t for t in value.split() if t]
        filtered = [t for t in tokens if t.upper() not in noise]
        return " ".join(filtered).strip()

    def _looks_like_noise_name(self, value: str) -> bool:
        """Эвристика для явного шума (заголовки, слипшиеся слова)."""
        if not value:
            return False
        up = value.upper()
        noise_fragments = ["SURNAME", "GIVEN", "NAME", "NAMES", "FIRST", "PASSPORT"]
        if any(n in up for n in noise_fragments):
            return True
        # Если слишком мало гласных
        vowels = sum(1 for c in up if c in "AEIOUY")
        if vowels == 0 and len(up) > 4:
            return True
        # Если одно слово длиннее 10 без пробелов и содержит не меньше 3 повторов одной буквы
        if " " not in value and len(up) >= 10 and max(up.count(c) for c in set(up)) >= 3:
            return True
        return False

    def parse_mrz(self, text: str, mrz_specialized_text: str = "") -> dict:
        """Парсинг MRZ (Machine Readable Zone) - строка внизу паспорта

        Args:
            text: Основной OCR текст
            mrz_specialized_text: Специализированный OCR только для MRZ зоны (только латиница)
        """
        mrz_data = {}

        # Если есть специализированный MRZ текст - используем его в первую очередь
        if mrz_specialized_text and self.debug:
            print(f"🎯 Используем специализированный MRZ OCR (только латиница)")

        # Пробуем сначала специализированный текст, потом основной
        text_to_parse = mrz_specialized_text if mrz_specialized_text else text

        raw_lines = [line.strip().replace(" ", "") for line in text_to_parse.splitlines()]

        # Если используем специализированный текст - разрешаем только латиницу
        if mrz_specialized_text:
            # Только латиница, цифры и <
            mrz_lines = [re.sub(r'[^A-Z0-9<]', '', line, flags=re.IGNORECASE) for line in raw_lines if len(re.sub(r'[^A-Z0-9<]', '', line, flags=re.IGNORECASE)) >= 25]
        else:
            # Расширяем для поддержки кириллицы в MRZ (fallback)
            mrz_lines = [re.sub(r'[^A-ZА-ЯӘӨҮҰҒҚҢҺІЁ0-9<]', '', line, flags=re.IGNORECASE) for line in raw_lines if len(re.sub(r'[^A-ZА-ЯӘӨҮҰҒҚҢҺІЁ0-9<]', '', line, flags=re.IGNORECASE)) >= 25]

        # Проверяем качество MRZ строк - отфильтровываем явный мусор
        if len(mrz_lines) >= 2:
            # Проверяем первую строку на наличие служебных слов (признак что это не MRZ)
            noise_words = ["MINISTRY", "INTERNAL", "AFFAIRS", "PASSPORT", "NATIONALITY", "REPUBLIC"]
            line1_upper = mrz_lines[0].upper() if mrz_lines else ""
            is_noise = any(word in line1_upper for word in noise_words)

            if is_noise:
                if self.debug:
                    print(f"⚠️ MRZ строки содержат служебные слова (не настоящий MRZ), ищем паттерны")
                mrz_lines = []  # Сбрасываем чтобы перейти к поиску паттернов

        if len(mrz_lines) < 2:
            # Ищем паттерн с шевронами (OCR может видеть << как < <, \< < и т.д.)
            # Ищем в ИСХОДНОМ тексте (включая короткие строки)
            patterns = [
                r'([A-ZА-ЯӘӨҮҰҒҚҢҺІЁ0-9]{3,})\s*<<\s*([A-ZА-ЯӘӨҮҰҒҚҢҺІЁ0-9]{3,})',  # стандартный <<
                r'([A-ZА-ЯӘӨҮҰҒҚҢҺІЁ0-9]{3,})\s*<\s*<\s*([A-ZА-ЯӘӨҮҰҒҚҢҺІЁ0-9]{3,})',  # < <
                r'([A-ZА-ЯӘӨҮҰҒҚҢҺІЁ0-9]{3,})\\<\s*<\s*([A-ZА-ЯӘӨҮҰҒҚҢҺІЁ0-9]{3,})',  # \< <
                r'([A-ZА-ЯӘӨҮҰҒҚҢҺІЁ0-9]{3,})<\s+<\s*([A-ZА-ЯӘӨҮҰҒҚҢҺІЁ0-9]{3,})',  # < <
                # Дополнительные паттерны для плохих сканов (только одно имя с шевронами)
                r'([A-ZА-ЯӘӨҮҰҒҚҢҺІЁ]{4,})\s*<{3,}',  # Имя с минимум 3 шевронами (FATULLA <<<<)
            ]

            for pattern in patterns:
                match = re.search(pattern, text_to_parse, re.IGNORECASE)
                if match:
                    last_name = match.group(1).replace("<", "").replace("\\", "").strip()
                    # Проверяем есть ли вторая группа (имя)
                    try:
                        first_name = match.group(2).replace("<", "").replace("\\", "").strip()
                    except IndexError:
                        # Паттерн нашёл только одно слово (например FATULLA <<<<)
                        # Пока не ясно это фамилия или имя - сохраним как имя
                        first_name = last_name
                        last_name = ""

                    if self.debug:
                        print(f"  📍 Найден MRZ паттерн:")
                        print(f"     Исходная фамилия: '{last_name}'")
                        print(f"     Исходное имя:     '{first_name}'")

                    # Проверяем на кириллицу и цифры (признак ошибок OCR)
                    last_had_issues = self._contains_cyrillic(last_name) or any(c.isdigit() for c in last_name)
                    first_had_issues = self._contains_cyrillic(first_name) or any(c.isdigit() for c in first_name)

                    # Транслитерируем если кириллица
                    if self._contains_cyrillic(last_name):
                        if self.debug:
                            print(f"     ⚠️  Фамилия на кириллице, транслитерируем...")
                        last_name = self._transliterate(last_name)
                    last_name = self._normalize_token(last_name)
                    if self.debug:
                        print(f"     ✅ После транслитерации: '{last_name}'")

                    if self._contains_cyrillic(first_name):
                        if self.debug:
                            print(f"     ⚠️  Имя на кириллице, транслитерируем...")
                        first_name = self._transliterate(first_name)
                    first_name = self._normalize_token(first_name)
                    if self.debug:
                        print(f"     ✅ После транслитерации: '{first_name}'")

                    mrz_data["last_name"] = last_name
                    mrz_data["first_name"] = first_name
                    mrz_data["last_had_issues"] = last_had_issues
                    mrz_data["first_had_issues"] = first_had_issues
                    if self.debug:
                        print(f"✅ MRZ (pattern): {mrz_data['last_name']} {mrz_data.get('first_name', '')}")
                    return mrz_data

            return mrz_data

        line1, line2 = mrz_lines[-2], mrz_lines[-1]
        if self.debug:
            print(f"✅ MRZ строка 1 (raw): {line1}")
            print(f"✅ MRZ строка 2 (raw): {line2}")

        # Обрабатываем стандартный формат MRZ
        if line1.startswith("P<"):
            # Формат: P<XXX где XXX = код страны (3 буквы)
            # После кода страны идет фамилия
            if len(line1) > 5:
                # P< + 3 буквы кода = 5 символов
                name_field = line1[5:]
            else:
                name_field = line1[2:]  # Fallback: просто убираем P<
        else:
            name_field = line1

        # Разделяем по двойным шевронам
        name_part = name_field.split("<<", 1)
        if name_part:
            last_name_raw = name_part[0].replace("<", "")
            # Проверяем на кириллицу и цифры (признак ошибок OCR)
            last_had_issues = self._contains_cyrillic(last_name_raw) or any(c.isdigit() for c in last_name_raw)

            # Транслитерируем если кириллица
            if self._contains_cyrillic(last_name_raw):
                if self.debug:
                    print(f"⚠️ MRZ фамилия на кириллице: {last_name_raw}")
            last_name_raw = self._transliterate(last_name_raw)
            last_name_raw = self._normalize_token(last_name_raw)
            if self.debug:
                print(f"✅ После транслитерации: {last_name_raw}")
            mrz_data["last_name"] = last_name_raw
            mrz_data["last_had_issues"] = last_had_issues

            first_had_issues = False
            if len(name_part) > 1:
                # Убираем одинарные шевроны и лишние пробелы
                first_name_raw = name_part[1].replace("<", " ").strip()
                first_had_issues = self._contains_cyrillic(first_name_raw) or any(c.isdigit() for c in first_name_raw)
                if self._contains_cyrillic(first_name_raw):
                    if self.debug:
                        print(f"⚠️ MRZ имя на кириллице: {first_name_raw}")
                first_name_raw = self._transliterate(first_name_raw)
                first_name_raw = self._normalize_token(first_name_raw)
                if self.debug:
                    print(f"✅ После транслитерации: {first_name_raw}")
                mrz_data["first_name"] = first_name_raw
                mrz_data["first_had_issues"] = first_had_issues
            elif not mrz_data.get("first_name"):
                # Если нет двойных шевронов, пробуем разделить по одинарным
                name_parts = name_field.replace("<", " ").split()
                if len(name_parts) > 1:
                    last_name_raw = name_parts[0]
                    first_name_raw = " ".join(name_parts[1:])
                    last_had_issues = self._contains_cyrillic(last_name_raw) or any(c.isdigit() for c in last_name_raw)
                    first_had_issues = self._contains_cyrillic(first_name_raw) or any(c.isdigit() for c in first_name_raw)
                    if self._contains_cyrillic(last_name_raw):
                        last_name_raw = self._transliterate(last_name_raw)
                    if self._contains_cyrillic(first_name_raw):
                        first_name_raw = self._transliterate(first_name_raw)
                    last_name_raw = self._normalize_token(last_name_raw)
                    first_name_raw = self._normalize_token(first_name_raw)
                    mrz_data["last_name"] = last_name_raw
                    mrz_data["first_name"] = first_name_raw
                    mrz_data["last_had_issues"] = last_had_issues
                    mrz_data["first_had_issues"] = first_had_issues

        if len(line2) >= 10:
            doc_field = line2[0:9]
            doc_check = line2[9]
            doc_number = doc_field.replace("<", "")
            if doc_number and re.match(r"^[A-Z0-9]{7,9}$", doc_number):
                if doc_check.isdigit() and self._calculate_mrz_check_digit(doc_field) == int(doc_check):
                    mrz_data["document_number"] = doc_number
                elif doc_number:
                    mrz_data["document_number"] = doc_number

        raw_exp = line2[21:27] if len(line2) >= 27 else ""
        exp_check = line2[27] if len(line2) >= 28 else ""
        exp_date = self._mrz_date_to_iso(raw_exp)
        if exp_date:
            if exp_check.isdigit() and self._calculate_mrz_check_digit(raw_exp) == int(exp_check):
                mrz_data["expiration_date"] = exp_date
            elif not exp_check:
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

    def parse_text(self, text: str, mrz_specialized_text: str = "") -> PassportData:
        """Основной парсинг текста паспорта

        Args:
            text: Основной OCR текст
            mrz_specialized_text: Специализированный OCR только для MRZ зоны
        """
        data = PassportData()

        if self.debug:
            print("\n" + "="*60)
            print("🔍 НАЧАЛО ПАРСИНГА")
            print("="*60)

        # 0. Телефон (если вдруг попал в скан)
        phone_match = re.search(r'(?:\+7|8)\s?\(?\d{3}\)?\s?\d{3}[\s-]?\d{2}[\s-]?\d{2}', text)
        if phone_match:
            data.phone = phone_match.group(0)

        # 1. ИИН (12 цифр подряд)
        iin_candidates = re.findall(r'\b(\d{12})\b', text)
        chosen_iin = ""
        for cand in iin_candidates:
            if self.validate_iin_checksum(cand):
                chosen_iin = cand
                break
        if not chosen_iin and iin_candidates:
            chosen_iin = iin_candidates[0]  # берем первый, если чек-сумма не прошла

        if chosen_iin:
            data.iin = chosen_iin
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

        raw_last_name = ""
        for pattern in surname_patterns:
            surname_match = re.search(pattern, text, re.IGNORECASE)
            if surname_match:
                raw_last_name = surname_match.group(1).strip()
                # Парсим все строки и выбираем латиницу если есть
                lines = raw_last_name.split('\n')
                best_line = None
                best_score = -1
                best_vowels = -1
                for line in lines:
                    clean = line.strip()
                    if not clean or not re.match(r'^[A-ZА-ЯӘӨҮҰҒҚҢҺІЁ\s]+$', clean):
                        continue
                    latin_count = sum(1 for c in clean if 'A' <= c.upper() <= 'Z')
                    cyr_count = sum(1 for c in clean if 'А' <= c.upper() <= 'Я' or c in "ЁӘӨҮҰҒҚҢҺІ")
                    vowel_count = sum(1 for c in clean if c.upper() in "AEIOUY")
                    score = latin_count * 2 - cyr_count
                    if (
                        score > best_score
                        or (score == best_score and vowel_count > best_vowels)
                        or (score == best_score and vowel_count == best_vowels)
                    ):
                        best_score = score
                        best_vowels = vowel_count
                        best_line = clean

                if best_line:
                    normalized = self._normalize_token(best_line)
                    data.last_name = normalized or best_line
                    if self.debug:
                        print(f"✅ Фамилия: {data.last_name}")
                break

        # Имя
        name_patterns = [
            r'(?:АТЫ|Given\s*names?|First\s*Names?)[\s:]*\n+([A-ZА-ЯӘӨҮҰҒҚҢҺІЁ\s\n]+)',
            r'GIVEN\s*NAMES?[\s:]*\n+([A-ZА-ЯӘӨҮҰҒҚҢҺІЁ\s\n]+)',
            r'АТЫ[^\n]*\n+([A-ZА-ЯӘӨҮҰҒҚҢҺІЁ\s\n]+)',
        ]

        for pattern in name_patterns:
            name_match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if name_match:
                name_text = name_match.group(1).strip()
                lines = [ln.strip() for ln in name_text.split('\n') if ln.strip()]
                if lines:
                    best_line = max(lines, key=lambda l: sum(1 for c in l if 'A' <= c.upper() <= 'Z'))
                    cleaned = self._normalize_token(best_line)
                    if cleaned and len(cleaned) > 2 and "PASSPORT" not in cleaned.upper():
                        parts = cleaned.split()
                        if len(parts) > 1 and len(parts[0]) <= 3 and len(parts[1]) > 3:
                            cleaned = parts[1]  # отбрасываем служебный префикс вроде ZH
                        data.first_name = cleaned
                        if self.debug:
                            print(f"✅ Найдено имя: {data.first_name}")
                        break

        # Доп. эвристика: если имя все ещё пустое, берем латиницу из текста без служебных слов
        if not data.first_name:
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            latin_lines = []
            for ln in lines:
                cleaned = self._normalize_token(ln)
                if not cleaned or len(cleaned) < 2 or len(cleaned) > 30:
                    continue
                up = cleaned.upper()
                if any(x in up for x in ["PASSPORT", "KAZ", "NATIONALITY", "MINISTRY"]):
                    continue
                if up == (data.last_name or "").upper():
                    continue
                latin_lines.append(cleaned)
            if latin_lines:
                data.first_name = latin_lines[0]
                if self.debug:
                    print(f"✅ Имя по латинице из текста: {data.first_name}")

        # Доп. fallback для фамилии: ищем любую подходящую строку, если ещё пусто
        if not data.last_name:
            for ln in text.splitlines():
                cleaned = self._normalize_token(ln)
                if not cleaned or len(cleaned) < 4 or len(cleaned) > 25:
                    continue
                up = cleaned.upper()
                if any(x in up for x in ["PASSPORT", "KAZ", "NATIONALITY", "MINISTRY", "GIVEN", "SURNAME"]):
                    continue
                if data.first_name and up == data.first_name.upper():
                    continue
                parts = cleaned.split()
                if len(parts) > 1 and len(parts[-1]) <= 2:
                    cleaned = " ".join(parts[:-1])
                data.last_name = cleaned
                if self.debug:
                    print(f"✅ Фамилия (fallback): {data.last_name}")
                break

        # ВАЖНО: Проверяем, не попали ли оба имени в одно поле
        if data.last_name and not data.first_name:
            # Если в фамилии несколько слов, возможно там и имя тоже
            if len(data.last_name.split()) > 1:
                if self.debug:
                    print(f"⚠️ Обнаружено несколько слов в фамилии: {data.last_name}")
                # Применяем умное разделение
                split_last, split_first = self._smart_name_split(data.last_name)
                if split_first:  # Если удалось разделить
                    data.last_name = split_last
                    data.first_name = split_first
                    if self.debug:
                        print(f"✅ После разделения - Фамилия: {data.last_name}, Имя: {data.first_name}")

        elif data.first_name and not data.last_name:
            # Если имя есть, а фамилии нет - возможно все в имени
            if len(data.first_name.split()) > 1:
                if self.debug:
                    print(f"⚠️ Обнаружено несколько слов в имени: {data.first_name}")
                split_last, split_first = self._smart_name_split(data.first_name)
                data.last_name = split_last
                data.first_name = split_first
                if self.debug:
                    print(f"✅ После разделения - Фамилия: {data.last_name}, Имя: {data.first_name}")

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

        # 6. MRZ OVERRIDE (самый точный источник имен после транслитерации)
        mrz_data = self.parse_mrz(text, mrz_specialized_text)

        # Используем MRZ если он не пустой (теперь там всегда латиница после транслитерации)
        use_mrz = False
        if mrz_data.get("last_name"):
            mrz_last = mrz_data["last_name"]
            mrz_first = mrz_data.get("first_name", "")

            # Сохраняем для словаря (чтобы фронт брал латиницу)
            data.mrz_last_name = mrz_last
            data.mrz_first_name = mrz_first

            # Проверяем качество MRZ: есть ли в нем хотя бы 2 буквы
            if len(mrz_last) >= 2 and mrz_last.replace(" ", "").isalpha():
                use_mrz = True

                # Если MRZ есть, используем его как приоритетный источник имен
                if mrz_last and not mrz_first and len(mrz_last.split()) > 1:
                    if self.debug:
                        print(f"⚠️ MRZ: Несколько слов в фамилии: {mrz_last}")
                    split_last, split_first = self._smart_name_split(mrz_last)
                    data.last_name = split_last
                    data.first_name = split_first
                    if self.debug:
                        print(f"✅ MRZ после разделения - Фамилия: {data.last_name}, Имя: {data.first_name}")
                else:
                    # Решаем, чем заменить: MRZ или текст, чтобы не потерять верные текстовые имена
                    def should_replace(text_val: str, mrz_val: str, mrz_had_issues: bool = False) -> bool:
                        if not mrz_val:
                            return False
                        mrz_q = self._name_quality(mrz_val)
                        text_q = self._name_quality(text_val)
                        similar = self._are_similar_words(mrz_val.replace(" ", ""), (text_val or "").replace(" ", ""))

                        if not text_val:
                            return True
                        if self._contains_cyrillic(text_val):
                            return True
                        if self._looks_like_noise_name(text_val):
                            return True

                        # КЛЮЧЕВОЕ ПРАВИЛО 1: Если MRZ БЕЗ ошибок (чистая латиница) - ОБЫЧНО используем MRZ!
                        # НО проверяем: возможно текст это более короткая и правильная версия
                        if not mrz_had_issues:
                            if mrz_q >= 4:  # MRZ качественный (минимум 4 буквы)
                                # Дополнительная проверка: если текст короче MRZ и очень похож,
                                # возможно в MRZ лишние символы (ошибка OCR)
                                if text_q >= 4 and len(text_val) < len(mrz_val):
                                    # Проверяем: MRZ содержит текст как подстроку (с небольшими отличиями)
                                    mrz_clean = mrz_val.replace(" ", "").upper()
                                    text_clean = text_val.replace(" ", "").upper()

                                    # Если текст является частью MRZ или очень похож (расстояние <= 1)
                                    if text_clean in mrz_clean or self._levenshtein_distance(text_clean, mrz_clean) == 1:
                                        if self.debug:
                                            print(f"   ⚠️  MRZ содержит лишние символы, текст точнее: {text_val}")
                                        return False

                                if self.debug:
                                    print(f"   ✅ MRZ чистый (без ошибок OCR), используем его: {mrz_val}")
                                return True

                        # КЛЮЧЕВОЕ ПРАВИЛО 2: Если MRZ был с ошибками OCR (кириллица/цифры),
                        # а текст чистый латинский и качественный - предпочитаем текст
                        if mrz_had_issues and text_q >= 4:  # минимум 4 буквы в тексте
                            if self.debug:
                                print(f"   ⚠️  MRZ был с ошибками OCR, используем чистый текст: {text_val}")
                            return False

                        # Дополнительная эвристика: если слова очень похожи и MRZ немного лучше
                        if similar and mrz_q > text_q:
                            if self.debug:
                                print(f"   ℹ️  Слова похожи, но MRZ качественнее: {mrz_val}")
                            return True

                        # Если не похожи, требуем значительного преимущества MRZ
                        if not similar and mrz_q >= text_q + 2:
                            return True

                        return False

                    mrz_last_had_issues = mrz_data.get("last_had_issues", False)
                    mrz_first_had_issues = mrz_data.get("first_had_issues", False)

                    if should_replace(data.last_name, mrz_last, mrz_last_had_issues):
                        data.last_name = mrz_last
                        if self.debug:
                            print(f"✅ Фамилия (MRZ): {data.last_name}")
                    else:
                        if self.debug and data.last_name:
                            print(f"✅ Фамилия (текст): {data.last_name}")

                    if should_replace(data.first_name, mrz_first, mrz_first_had_issues):
                        data.first_name = mrz_first
                        if self.debug:
                            print(f"✅ Имя (MRZ): {data.first_name}")
                    else:
                        if self.debug and data.first_name:
                            print(f"✅ Имя (текст): {data.first_name}")
            else:
                if self.debug:
                    print(f"⚠️ MRZ фамилия некачественная: '{mrz_last}'")

        # Если текстовые поля всё ещё на кириллице — транслитерируем
        if self._contains_cyrillic(data.last_name):
            old_last = data.last_name
            data.last_name = self._transliterate(data.last_name)
            if self.debug:
                print(f"🔄 Транслитерация фамилии: {old_last} → {data.last_name}")

        if self._contains_cyrillic(data.first_name):
            old_first = data.first_name
            data.first_name = self._transliterate(data.first_name)
            if self.debug:
                print(f"🔄 Транслитерация имени: {old_first} → {data.first_name}")

        # Убираем служебные слова/мусор после всех замен
        data.last_name = self._remove_noise_tokens(data.last_name)
        data.first_name = self._remove_noise_tokens(data.first_name)

        if mrz_data.get("document_number"):
            data.document_number = mrz_data["document_number"]
            if self.debug:
                print(f"✅ Номер документа (MRZ): {data.document_number}")
        if mrz_data.get("expiration_date"):
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
        text, mrz_text = self.extract_ocr_text(file_path)
        return self.parse_text(text, mrz_text)


# Функция для быстрого тестирования
def test_parser(file_path: str):
    parser = PassportParser(debug=True)
    result = parser.parse(file_path)
    print("\n🎯 РЕЗУЛЬТАТ:")
    print(result.to_dict())
    return result
