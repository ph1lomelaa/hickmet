# 📡 API Documentation - Admin Endpoints

## Base URL
```
http://127.0.0.1:8000
# Или ваш production URL
https://api.yourdomain.com
```

---

## 📊 GET `/api/admin/analytics`

Получение полной аналитики за период

### Parameters:
- `start_date` (required): YYYY-MM-DD
- `end_date` (required): YYYY-MM-DD

### Example Request:
```bash
curl "http://127.0.0.1:8000/api/admin/analytics?start_date=2024-12-01&end_date=2024-12-18"
```

### Example Response:
```json
{
  "ok": true,
  "total_bookings": 150,
  "total_cancelled": 15,
  "cancellation_rate": 9.09,
  "top_packages": [
    ["NIYET 7 DAYS", 45],
    ["HIKMA 11 DAYS", 32],
    ["IZI SWISSOTEL", 28]
  ],
  "managers_rating": [
    ["Айгуль Менеджер", 50, 5],
    ["Асем Продавец", 45, 3],
    ["Диана Консультант", 40, 2]
  ],
  "popular_rooms": [
    ["Quad", 60],
    ["Triple", 45],
    ["Double", 30]
  ],
  "daily_dynamics": [
    ["2024-12-01", 8],
    ["2024-12-02", 12],
    ["2024-12-03", 10]
  ]
}
```

---

## 👥 GET `/api/admin/managers`

Получение списка всех менеджеров

### Example Request:
```bash
curl "http://127.0.0.1:8000/api/admin/managers"
```

### Example Response:
```json
{
  "ok": true,
  "managers": [
    {
      "telegram_id": 123456789,
      "full_name": "Айгуль Менеджер",
      "username": "aigul_manager",
      "role": "manager"
    },
    {
      "telegram_id": 987654321,
      "full_name": "Админ Главный",
      "username": "main_admin",
      "role": "admin"
    }
  ]
}
```

---

## 📈 GET `/api/admin/manager/{manager_id}`

Детальная статистика по конкретному менеджеру

### Parameters:
- `manager_id` (path): Telegram ID менеджера
- `start_date` (query, required): YYYY-MM-DD
- `end_date` (query, required): YYYY-MM-DD

### Example Request:
```bash
curl "http://127.0.0.1:8000/api/admin/manager/123456789?start_date=2024-12-01&end_date=2024-12-18"
```

### Example Response:
```json
{
  "ok": true,
  "total": 50,
  "active": 45,
  "cancelled": 5,
  "top_packages": [
    ["NIYET 7 DAYS", 20],
    ["HIKMA 11 DAYS", 15],
    ["IZI SWISSOTEL", 10]
  ],
  "bookings": [
    {
      "id": 1,
      "guest_last_name": "IVANOV",
      "guest_first_name": "IVAN",
      "package_name": "NIYET 7 DAYS",
      "sheet_name": "17.12-24.12 Ala-Jed",
      "price": "450000",
      "status": "new",
      "created_at": "2024-12-15T10:30:00"
    }
  ]
}
```

---

## 🔍 GET `/api/admin/search/packages`

Поиск пакетов по дате

### Parameters:
- `date` (query, required): ДД.ММ (например: "17.12")

### Example Request:
```bash
curl "http://127.0.0.1:8000/api/admin/search/packages?date=17.12"
```

### Example Response:
```json
{
  "ok": true,
  "packages": [
    {
      "sheet_name": "17.12-24.12 Ala-Jed",
      "package_name": "NIYET 7 DAYS",
      "count": 25
    },
    {
      "sheet_name": "17.12-28.12 Dubai",
      "package_name": "HIKMA 11 DAYS",
      "count": 18
    }
  ]
}
```

---

## 🐍 Python Examples

### Получение аналитики:
```python
import requests
from datetime import datetime, timedelta

# Аналитика за последние 30 дней
end_date = datetime.now().date()
start_date = end_date - timedelta(days=30)

response = requests.get(
    'http://127.0.0.1:8000/api/admin/analytics',
    params={
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat()
    }
)

data = response.json()
print(f"Всего продаж: {data['total_bookings']}")
print(f"Процент отмен: {data['cancellation_rate']}%")
```

### Статистика менеджера:
```python
manager_id = 123456789

response = requests.get(
    f'http://127.0.0.1:8000/api/admin/manager/{manager_id}',
    params={
        'start_date': '2024-12-01',
        'end_date': '2024-12-18'
    }
)

data = response.json()
if data['ok']:
    print(f"Активных броней: {data['active']}")
    print(f"Отменено: {data['cancelled']}")
    print("Топ пакетов:")
    for pkg_name, count in data['top_packages']:
        print(f"  - {pkg_name}: {count}")
```

---

## 🔐 Добавление аутентификации (опционально)

Если хотите защитить API:

### 1. Добавьте в `api_server.py`:
```python
from fastapi import Header, HTTPException

ADMIN_API_KEY = "your_secret_key_here"

async def verify_admin(x_api_key: str = Header()):
    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
```

### 2. Добавьте в endpoint:
```python
@app.get("/api/admin/analytics", dependencies=[Depends(verify_admin)])
async def get_admin_analytics(...):
    ...
```

### 3. Используйте в запросах:
```bash
curl -H "X-API-Key: your_secret_key_here" \
     "http://127.0.0.1:8000/api/admin/analytics?start_date=2024-12-01&end_date=2024-12-18"
```

---

## 🧪 Тестирование API

### Используя httpie:
```bash
# Установка
pip install httpie

# Запросы
http GET "http://127.0.0.1:8000/api/admin/analytics?start_date=2024-12-01&end_date=2024-12-18"
http GET "http://127.0.0.1:8000/api/admin/managers"
```

### Используя Postman:
1. Импортируйте следующую коллекцию
2. Замените `{{base_url}}` на ваш URL
3. Готово!

---

## 📝 Error Responses

### 400 Bad Request:
```json
{
  "ok": false,
  "error": "Invalid date format"
}
```

### 404 Not Found:
```json
{
  "ok": false,
  "error": "Manager not found"
}
```

### 500 Internal Server Error:
```json
{
  "ok": false,
  "error": "Database connection error"
}
```

---

## 🚀 Rate Limiting (рекомендуется)

Добавьте rate limiting для защиты API:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/api/admin/analytics")
@limiter.limit("30/minute")
async def get_admin_analytics(request: Request, ...):
    ...
```

---

## 📚 Дополнительные ресурсы:

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Telegram WebApp API](https://core.telegram.org/bots/webapps)
- [Chart.js Docs](https://www.chartjs.org/docs/)

---

**Happy Coding! 🎉**
