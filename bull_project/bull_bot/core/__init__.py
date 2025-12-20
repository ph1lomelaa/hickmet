def __init__(self, db_path: str = 'bull_bot.db'):
    """Инициализация базы данных"""
    self.db_path = db_path
    self.init_database()
    self.fix_tables_structure()  # ← ДОБАВЬ ЭТУ СТРОКУ