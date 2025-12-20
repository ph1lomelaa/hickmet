import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from .models import Base

# Находим корень проекта, чтобы путь был всегда верным
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "bull_database.db")

# Берем URL из переменной окружения, по умолчанию используем локальный SQLite
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DB_PATH}")

engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    """Создает таблицы, если их нет. Вызывать при старте main.py и api_server.py"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(f"✅ База данных инициализирована по адресу: {DATABASE_URL}")
