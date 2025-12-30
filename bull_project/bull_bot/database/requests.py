from sqlalchemy import select, desc, func, distinct, or_, text
from datetime import datetime, timedelta
from .models import User, Booking, Request4U, AdminSettings, ApprovalRequest
from .setup import async_session, engine


async def ensure_group_members_column():
    """
    Мягко добавляем колонку group_members, если ее еще нет (SQLite/Postgres).
    Ошибки игнорируем, чтобы не падать при повторном вызове.
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE bookings ADD COLUMN group_members TEXT"))
            print("✅ Колонка group_members добавлена")
    except Exception as e:
        # Уже есть или нет прав — тихо игнорируем
        print(f"ℹ️ Колонка group_members уже существует или нет прав: {type(e).__name__}")
        pass

async def check_group_members_column_exists():
    """Проверяет, существует ли колонка group_members в таблице bookings"""
    try:
        async with engine.begin() as conn:
            # PostgreSQL
            result = await conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='bookings' AND column_name='group_members'
            """))
            exists = result.fetchone() is not None
            print(f"🔍 Проверка колонки group_members: {'существует' if exists else 'НЕ существует'}")
            return exists
    except Exception as e:
        # SQLite или другая ошибка - считаем что колонки нет
        print(f"⚠️ Не удалось проверить колонку group_members: {type(e).__name__}")
        return False

# === ПОЛЬЗОВАТЕЛИ ===

async def add_user(tg_id: int, full_name: str, username: str, role: str = "manager"):
    async with async_session() as session:
        # Проверяем, есть ли уже такой
        user = await session.scalar(select(User).where(User.telegram_id == tg_id))
        if user:
            # Если есть - обновляем имя (вдруг он решил перезайти с новым именем)
            user.full_name = full_name
            user.role = role
        else:
            # Если нет - создаем
            session.add(User(telegram_id=tg_id, full_name=full_name, username=username, role=role))
        await session.commit()


async def get_user_by_id(tg_id: int):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == tg_id))
        return user # Возвращаем весь объект (user.full_name, user.role)

async def get_user_role(tg_id: int):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == tg_id))
        return user.role if user else None

async def get_all_managers_list():
    """Возвращает список всех сотрудников"""
    async with async_session() as session:
        query = select(User).where(User.role.in_(['manager', 'admin', 'care']))
        result = await session.scalars(query)
        return result.all()

async def get_admin_ids():
    async with async_session() as session:
        query = select(User.telegram_id).where(User.role == "admin")
        result = await session.scalars(query)
        return result.all()

# === НАСТРОЙКИ АДМИНОВ ===
async def get_admin_settings(admin_id: int) -> AdminSettings:
    async with async_session() as session:
        settings = await session.get(AdminSettings, admin_id)
        return settings

async def set_admin_settings(admin_id: int, notify_new: bool = None, notify_cancel: bool = None, notify_reschedule: bool = None):
    async with async_session() as session:
        settings = await session.get(AdminSettings, admin_id)
        if not settings:
            settings = AdminSettings(admin_id=admin_id)
            session.add(settings)
        if notify_new is not None:
            settings.notify_new = 1 if notify_new else 0
        if notify_cancel is not None:
            settings.notify_cancel = 1 if notify_cancel else 0
        if notify_reschedule is not None:
            settings.notify_reschedule = 1 if notify_reschedule else 0
        await session.commit()

# === APPROVAL REQUESTS ===
async def create_approval_request(booking_id: int, request_type: str, initiator_id: int, comment: str = None) -> int:
    async with async_session() as session:
        req = ApprovalRequest(
            booking_id=booking_id,
            request_type=request_type,
            initiator_id=initiator_id,
            status="pending",
            comment=comment
        )
        session.add(req)
        await session.commit()
        await session.refresh(req)
        return req.id

async def update_approval_status(request_id: int, status: str):
    async with async_session() as session:
        req = await session.get(ApprovalRequest, request_id)
        if req:
            req.status = status
            await session.commit()

async def get_pending_requests():
    await ensure_group_members_column()
    async with async_session() as session:
        query = select(ApprovalRequest).where(ApprovalRequest.status == "pending").order_by(desc(ApprovalRequest.created_at))
        result = await session.scalars(query)
        return result.all()

async def get_approval_request(req_id: int):
    async with async_session() as session:
        return await session.get(ApprovalRequest, req_id)

async def delete_user(tg_id: int):
    async with async_session() as session:
        user = await session.get(User, tg_id)
        if user:
            user.role = "guest" # Мягкое удаление (сброс роли)
            await session.commit()

# === БРОНИРОВАНИЯ (ЗАПИСЬ) ===

async def add_booking_to_db(data: dict, manager_id: int):
    """Принимает словарь полей и создает запись Booking"""
    await ensure_group_members_column()

    print(f"\n💾 add_booking_to_db вызвана:")
    print(f"   manager_id: {manager_id}")
    print(f"   data keys: {list(data.keys())}")
    print(f"   group_members в data: {'group_members' in data}")

    # 🔥 КРИТИЧЕСКИЙ ФИКС: Проверяем, существует ли колонка group_members
    # Если нет - удаляем из data, чтобы не упасть
    column_exists = await check_group_members_column_exists()

    if not column_exists and 'group_members' in data:
        print(f"   ⚠️ ВНИМАНИЕ: Колонка group_members НЕ существует в БД!")
        print(f"   Временно удаляем group_members из data для сохранения...")
        removed_value = data.pop('group_members')
        print(f"   Удалено значение: {removed_value[:100] if removed_value else 'None'}...")
    elif 'group_members' in data:
        print(f"   group_members value: {data['group_members'][:100] if data['group_members'] else 'None'}...")

    try:
        async with async_session() as session:
            # manager_id берется отдельно, остальные поля из словаря
            print(f"   Создание объекта Booking...")
            booking = Booking(manager_id=manager_id, **data)
            print(f"   ✅ Объект создан, добавление в сессию...")
            session.add(booking)
            print(f"   Коммит в БД...")
            await session.commit()
            await session.refresh(booking)
            print(f"   ✅ Запись сохранена с ID: {booking.id}")
            return booking.id
    except Exception as e:
        print(f"❌ ОШИБКА в add_booking_to_db:")
        print(f"   Тип ошибки: {type(e).__name__}")
        print(f"   Сообщение: {str(e)}")
        import traceback
        traceback.print_exc()
        raise  # Пробрасываем ошибку дальше

async def update_booking_row(booking_id: int, row_num: int):
    """Обновляет номер строки после записи в Google"""
    async with async_session() as session:
        b = await session.get(Booking, booking_id)
        if b:
            b.sheet_row_number = row_num
            await session.commit()

async def mark_booking_cancelled(booking_id: int):
    """Помечает бронь как отмененную"""
    async with async_session() as session:
        b = await session.get(Booking, booking_id)
        if b:
            b.status = 'cancelled'
            await session.commit()

async def mark_booking_rescheduled(booking_id: int, comment: str = None):
    """Помечает бронь как перенесенную"""
    async with async_session() as session:
        b = await session.get(Booking, booking_id)
        if b:
            b.status = 'rescheduled'
            if comment:
                b.comment = comment
            await session.commit()

async def update_booking_fields(booking_id: int, fields: dict):
    """Обновляет указанные поля брони"""
    async with async_session() as session:
        b = await session.get(Booking, booking_id)
        if b:
            for key, value in fields.items():
                if hasattr(b, key):
                    setattr(b, key, value)
            await session.commit()

async def update_booking_passport_path(booking_id: int, passport_path: str):
    """Обновляет путь к файлу паспорта"""
    async with async_session() as session:
        b = await session.get(Booking, booking_id)
        if b:
            b.passport_image_path = passport_path
            await session.commit()

# === ИСТОРИЯ И ПОИСК ===

async def get_manager_packages(manager_id: int):
    """Возвращает список уникальных названий пакетов, которые продал менеджер"""
    async with async_session() as session:
        # Select distinct package_name
        stmt = select(distinct(Booking.package_name)).where(
            Booking.manager_id == manager_id,
            Booking.status.notin_(('cancelled', 'rescheduled'))
        ).order_by(desc(Booking.created_at))

        result = await session.scalars(stmt)
        return result.all()

async def get_bookings_in_package(manager_id: int, pkg_name: str):
    """Возвращает всех туристов менеджера в конкретном пакете"""
    async with async_session() as session:
        query = select(Booking).where(
            Booking.manager_id == manager_id,
            Booking.package_name == pkg_name,
            Booking.status.notin_(('cancelled', 'rescheduled'))
        ).order_by(desc(Booking.created_at))
        result = await session.scalars(query)
        return result.all()

async def get_booking_by_id(bid: int):
    async with async_session() as session:
        return await session.get(Booking, bid)

async def get_all_bookings_for_manager(manager_id: int):
    """Возвращает все брони менеджера, включая отмененные."""
    async with async_session() as session:
        query = select(Booking).where(
            Booking.manager_id == manager_id
        ).order_by(desc(Booking.created_at))
        result = await session.scalars(query)
        return result.all()

async def get_recent_bookings(limit: int = 30):
    """Возвращает последние N броней всех менеджеров (для демо-режима)."""
    async with async_session() as session:
        query = select(Booking).order_by(desc(Booking.created_at)).limit(limit)
        result = await session.scalars(query)
        return result.all()

async def search_tourist_by_name(query_str: str):
    """Поиск для Отдела Заботы"""
    async with async_session() as session:
        clean_query = " ".join((query_str or "").strip().split())
        if not clean_query:
            return []

        flex_search = f"%{'%'.join(clean_query.split())}%"
        compact_search = f"%{clean_query.replace(' ', '')}%"

        last = func.coalesce(Booking.guest_last_name, "")
        first = func.coalesce(Booking.guest_first_name, "")
        full_name = func.trim(func.concat(last, " ", first))
        full_name_rev = func.trim(func.concat(first, " ", last))

        stmt = select(Booking).where(
            Booking.status.notin_(('cancelled', 'rescheduled')),
            or_(
                Booking.guest_last_name.ilike(flex_search),
                Booking.guest_first_name.ilike(flex_search),
                full_name.ilike(flex_search),
                full_name_rev.ilike(flex_search),
                func.replace(full_name, " ", "").ilike(compact_search),
                func.replace(full_name_rev, " ", "").ilike(compact_search),
            )
        ).order_by(desc(Booking.created_at)).limit(10)

        result = await session.scalars(stmt)
        return result.all()

async def get_latest_passport_for_person(last_name: str, first_name: str):
    """Возвращает самый свежий путь к паспорту для паломника по ФИО."""
    async with async_session() as session:
        stmt = (
            select(Booking.passport_image_path)
            .where(
                Booking.guest_last_name == last_name,
                Booking.guest_first_name == first_name,
                Booking.passport_image_path.isnot(None),
                Booking.status.notin_(('cancelled', 'rescheduled'))
            )
            .order_by(desc(Booking.created_at))
            .limit(1)
        )
        res = await session.scalar(stmt)
        return res

async def get_db_packages_list(sheet_id: str, sheet_name: str):
    """Для Отдела Заботы: список пакетов на конкретной дате"""
    async with async_session() as session:
        # Ищем уникальные пакеты в базе, у которых совпадает table_id и sheet_name
        stmt = select(distinct(Booking.package_name)).where(
            Booking.table_id == sheet_id,
            Booking.sheet_name == sheet_name,
            Booking.status.notin_(('cancelled', 'rescheduled'))
        )
        result = await session.scalars(stmt)
        return result.all()

async def get_all_bookings_in_package(sheet_id: str, sheet_name: str, pkg_name: str):
    """Для Отдела Заботы: все люди в пакете"""
    # 🔥 ИСПРАВЛЕНИЕ: Убираем лишние пробелы
    sheet_id = sheet_id.strip() if sheet_id else sheet_id
    sheet_name = sheet_name.strip() if sheet_name else sheet_name
    pkg_name = pkg_name.strip() if pkg_name else pkg_name

    # 🔥 ДЕБАГ: Логирование запроса
    print(f"\n🔍 get_all_bookings_in_package - ЗАПРОС В БД:")
    print(f"   sheet_id: '{sheet_id}'")
    print(f"   sheet_name: '{sheet_name}' (длина: {len(sheet_name)})")
    print(f"   pkg_name: '{pkg_name}'")

    async with async_session() as session:
        query = select(Booking).where(
            Booking.table_id == sheet_id,
            Booking.sheet_name == sheet_name,
            Booking.package_name == pkg_name,
            Booking.status.notin_(('cancelled', 'rescheduled'))
        ).order_by(Booking.sheet_row_number)
        result = await session.scalars(query)
        bookings = result.all()

        print(f"   Результат: {len(bookings)} бронирований")
        return bookings

# === ОТЧЕТЫ (Admin) ===

async def get_manager_bookings_by_period(manager_id: int, period: str):
    async with async_session() as session:
        query = select(Booking).where(Booking.manager_id == manager_id, Booking.status.notin_(('cancelled', 'rescheduled')))
        now = datetime.now()

        if period == 'today':
            query = query.where(func.date(Booking.created_at) == now.date())
        elif period == 'week':
            query = query.where(Booking.created_at >= now - timedelta(days=7))
        elif period == 'month':
            query = query.where(Booking.created_at >= now - timedelta(days=30))

        result = await session.scalars(query.order_by(desc(Booking.created_at)))
        return result.all()

async def get_bookings_by_package_full(sheet_name: str, pkg_name: str):
    async with async_session() as session:
        query = select(Booking).where(
            Booking.sheet_name == sheet_name,
            Booking.package_name == pkg_name,
            Booking.status.notin_(('cancelled', 'rescheduled'))
        ).order_by(Booking.sheet_row_number)
        result = await session.scalars(query)
        return result.all()

# === 4U REQUESTS ===

async def add_4u_request(user_id, name, dates, count, room, table_id):
    async with async_session() as session:
        req = Request4U(
            manager_id=user_id,
            manager_name=name,
            dates=dates,
            pilgrim_count=count,
            room_type=room,
            table_id=table_id  # 🔥 Сохраняем ID таблицы
        )
        session.add(req)
        await session.commit()
        return req.id

async def get_4u_request_by_id(rid):
    async with async_session() as session:
        return await session.get(Request4U, rid)

async def close_4u_request(rid):
    async with async_session() as session:
        r = await session.get(Request4U, rid)
        if r: r.status = "done"; await session.commit()

# === RNP ===
async def get_rnp_by_specific_date(date_obj):
    async with async_session() as session:
        return await session.scalar(select(func.count(Booking.id)).where(func.date(Booking.created_at) == date_obj, Booking.status.notin_(('cancelled', 'rescheduled')))) or 0

async def get_rnp_by_date_range(d1, d2):
    async with async_session() as session:
        return await session.scalar(select(func.count(Booking.id)).where(func.date(Booking.created_at) >= d1, func.date(Booking.created_at) <= d2, Booking.status.notin_(('cancelled', 'rescheduled')))) or 0

async def get_sales_dynamics_stats(days=10):
    async with async_session() as session:
        start = datetime.now().date() - timedelta(days=days)
        stmt = select(func.date(Booking.created_at).label('d'), func.count(Booking.id)).where(Booking.status.notin_(('cancelled', 'rescheduled')), func.date(Booking.created_at) >= start).group_by('d').order_by('d')
        res = await session.execute(stmt)
        return res.all()

async def get_all_bookings_by_period(start_date, end_date):
    """Все брони всех менеджеров за период"""
    async with async_session() as session:
        query = select(Booking).where(
            Booking.status.notin_(('cancelled', 'rescheduled')),
            func.date(Booking.created_at) >= start_date,
            func.date(Booking.created_at) <= end_date
        ).order_by(desc(Booking.created_at))
        result = await session.scalars(query)
        return result.all()

async def get_last_n_bookings_by_manager(manager_id: int, limit=10, include_cancelled: bool = False):
    """Последние N броней менеджера (по умолчанию без отменённых)."""
    await ensure_group_members_column()
    async with async_session() as session:
        query = select(Booking).where(Booking.manager_id == manager_id)
        if not include_cancelled:
            query = query.where(Booking.status.notin_(('cancelled', 'rescheduled')))
        query = query.order_by(desc(Booking.created_at)).limit(limit)
        result = await session.scalars(query)
        return result.all()

async def get_active_4u_requests():
    """Возвращает все заявки со статусом 'pending'"""
    async with async_session() as session:
        # Сортируем: новые сверху (или уберите .order_by..., если хотите старые сверху)
        query = select(Request4U).where(Request4U.status == 'pending').order_by(desc(Request4U.created_at))
        result = await session.scalars(query)
        return result.all()
async def get_detailed_stats_by_period(start_date, end_date):
    """
    Сложный отчет:
    1. Общее кол-во
    2. Топ 10 пакетов (ИЗМЕНИЛИ ЛИМИТ)
    3. Статистика по каждому менеджеру
    """
    async with async_session() as session:
        # 1. Общее
        total = await session.scalar(
            select(func.count(Booking.id)).where(
                Booking.status.notin_(('cancelled', 'rescheduled')),
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            )
        ) or 0

        # 2. Топ 10 Пакетов (LIMIT 10)
        top_pkg_stmt = (
            select(Booking.package_name, func.count(Booking.id).label('cnt'))
            .where(
                Booking.status.notin_(('cancelled', 'rescheduled')),
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            )
            .group_by(Booking.package_name)
            .order_by(desc('cnt'))
            .limit(10) # <--- БЫЛО 3, СТАЛО 10
        )
        top_pkgs = (await session.execute(top_pkg_stmt)).all()

        # 3. Менеджеры
        man_stmt = (
            select(Booking.manager_name_text, func.count(Booking.id).label('cnt'))
            .where(
                Booking.status.notin_(('cancelled', 'rescheduled')),
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            )
            .group_by(Booking.manager_name_text)
            .order_by(desc('cnt'))
        )
        managers_stat = (await session.execute(man_stmt)).all()

        return {
            "total": total,
            "top_packages": top_pkgs,
            "managers": managers_stat
        }

async def get_bookings_by_manager_date_range(manager_id: int, start_date, end_date):
    """
    Ищет брони конкретного менеджера в диапазоне дат (включительно).
    Используется админом при выборе кастомного периода.
    """
    async with async_session() as session:
        query = select(Booking).where(
            Booking.manager_id == manager_id,
            Booking.status.notin_(('cancelled', 'rescheduled')),
            func.date(Booking.created_at) >= start_date,
            func.date(Booking.created_at) <= end_date
        ).order_by(desc(Booking.created_at))

        result = await session.scalars(query)
        return result.all()

async def get_4u_request_by_id(req_id: int):
    async with async_session() as session:
        return await session.get(Request4U, req_id)

async def update_4u_status(req_id: int, status: str, sheet_name: str = None):
    async with async_session() as session:
        req = await session.get(Request4U, req_id)
        if req:
            req.status = status
            if sheet_name: req.created_sheet_name = sheet_name
            await session.commit()

# === РАСШИРЕННАЯ АНАЛИТИКА ДЛЯ АДМИН WEBAPP ===

async def get_full_analytics(start_date, end_date):
    """
    Полная аналитика для админ панели:
    - Общая статистика
    - ТОП пакетов (все)
    - Рейтинг менеджеров
    - Статистика отмен
    - Самые популярные направления
    """
    async with async_session() as session:
        # 1. Общая статистика
        total_bookings = await session.scalar(
            select(func.count(Booking.id)).where(
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date,
                Booking.status.notin_(('cancelled', 'rescheduled'))
            )
        ) or 0

        total_cancelled = await session.scalar(
            select(func.count(Booking.id)).where(
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date,
                Booking.status == 'cancelled'
            )
        ) or 0

        # 2. ТОП пакетов (ВСЕ)
        top_packages_stmt = (
            select(Booking.package_name, func.count(Booking.id).label('cnt'))
            .where(
                Booking.status.notin_(('cancelled', 'rescheduled')),
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            )
            .group_by(Booking.package_name)
            .order_by(desc('cnt'))
        )
        top_packages = (await session.execute(top_packages_stmt)).all()

        # 3. Рейтинг менеджеров
        from sqlalchemy import case
        managers_stmt = (
            select(
                Booking.manager_name_text,
                func.count(Booking.id).label('total'),
                func.sum(
                    case((Booking.status == 'cancelled', 1), else_=0)
                ).label('cancelled_count')
            )
            .where(
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            )
            .group_by(Booking.manager_name_text)
            .order_by(desc('total'))
        )
        managers_rating = (await session.execute(managers_stmt)).all()

        # 4. Популярные типы номеров
        rooms_stmt = (
            select(Booking.room_type, func.count(Booking.id).label('cnt'))
            .where(
                Booking.status.notin_(('cancelled', 'rescheduled')),
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            )
            .group_by(Booking.room_type)
            .order_by(desc('cnt'))
        )
        popular_rooms = (await session.execute(rooms_stmt)).all()

        # 5. Дневная динамика
        daily_stmt = (
            select(
                func.date(Booking.created_at).label('date'),
                func.count(Booking.id).label('count')
            )
            .where(
                Booking.status.notin_(('cancelled', 'rescheduled')),
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            )
            .group_by('date')
            .order_by('date')
        )
        daily_dynamics = (await session.execute(daily_stmt)).all()

        return {
            "total_bookings": total_bookings,
            "total_cancelled": total_cancelled,
            "cancellation_rate": round((total_cancelled / (total_bookings + total_cancelled) * 100), 2) if (total_bookings + total_cancelled) > 0 else 0,
            "top_packages": [(name, cnt) for name, cnt in top_packages],
            "managers_rating": [(name, total, cancelled or 0) for name, total, cancelled in managers_rating],
            "popular_rooms": [(room, cnt) for room, cnt in popular_rooms],
            "daily_dynamics": [(str(date), cnt) for date, cnt in daily_dynamics]
        }

async def get_manager_detailed_stats(manager_id: int, start_date, end_date):
    """Детальная статистика по конкретному менеджеру"""
    async with async_session() as session:
        # Все брони
        bookings = await session.scalars(
            select(Booking).where(
                Booking.manager_id == manager_id,
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            ).order_by(desc(Booking.created_at))
        )
        all_bookings = bookings.all()

        # Активные
        active_count = sum(1 for b in all_bookings if b.status not in ('cancelled', 'rescheduled'))
        # Отмененные
        cancelled_count = sum(1 for b in all_bookings if b.status == 'cancelled')
        # Перенесенные
        rescheduled_count = sum(1 for b in all_bookings if b.status == 'rescheduled')

        # ТОП пакетов этого менеджера
        top_packages_stmt = (
            select(Booking.package_name, func.count(Booking.id).label('cnt'))
            .where(
                Booking.manager_id == manager_id,
                Booking.status.notin_(('cancelled', 'rescheduled')),
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            )
            .group_by(Booking.package_name)
            .order_by(desc('cnt'))
        )
        manager_top_packages = (await session.execute(top_packages_stmt)).all()

        return {
            "total": len(all_bookings),
            "active": active_count,
            "cancelled": cancelled_count,
            "rescheduled": rescheduled_count,
            "top_packages": [(name, cnt) for name, cnt in manager_top_packages],
            "bookings": all_bookings
        }

async def search_packages_by_date(date_str: str):
    """Поиск пакетов по дате (для админа)"""
    async with async_session() as session:
        # Ищем по sheet_name (содержит дату)
        search = f"%{date_str}%"
        packages_stmt = (
            select(
                Booking.sheet_name,
                Booking.package_name,
                func.count(Booking.id).label('cnt')
            )
            .where(
                Booking.sheet_name.like(search),
                Booking.status.notin_(('cancelled', 'rescheduled'))
            )
            .group_by(Booking.sheet_name, Booking.package_name)
            .order_by(desc('cnt'))
        )
        results = (await session.execute(packages_stmt)).all()
        return [(sheet, pkg, cnt) for sheet, pkg, cnt in results]

async def get_all_bookings_for_period(start_date, end_date):
    """Получение всех броней за период (для админа)"""
    async with async_session() as session:
        bookings = await session.scalars(
            select(Booking).where(
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            ).order_by(desc(Booking.created_at))
        )
        return bookings.all()
