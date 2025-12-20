FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

# Системные зависимости для tesseract/pdf2image/opencv
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-rus \
    libtesseract-dev \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Зависимости Python
COPY bull_project/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY bull_project /app/bull_project

# Пусть Python видит проект
ENV PYTHONPATH=/app

EXPOSE 8000

# Запускаем API-сервер
CMD ["python", "-m", "bull_project.bull_bot.core.api_server"]
