import sqlite3
import json
import logging
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

@dataclass
class TrackedItem:
    """Класс для отслеживаемого предмета"""
    id: Optional[int] = None
    chat_id: int = 0
    url: str = ""
    min_float: float = 0.0
    max_float: float = 0.0
    item_name: str = ""
    created_at: str = ""
    last_check: str = ""
    last_update: str = ""
    is_active: bool = True
    total_found: int = 0
    last_found_count: int = 0
    settings: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.settings is None:
            self.settings = {
                'notifications': True,
                'show_all_on_start': True,
                'check_interval': 1,
                'max_price': 100000
            }
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.last_update:
            self.last_update = self.created_at
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TrackedItem':
        return cls(**data)

@dataclass
class FoundItem:
    """Класс для найденного предмета"""
    id: Optional[int] = None
    tracked_item_id: int = 0
    item_id: str = ""
    float_value: float = 0.0
    price: str = ""
    condition: str = ""
    url: str = ""
    found_at: str = ""
    is_notified: bool = False
    is_active: bool = True
    
    def __post_init__(self):
        if not self.found_at:
            self.found_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return asdict(self)

class Database:
    """Класс для работы с базой данных SQLite"""
    
    def __init__(self, db_path: str = "items.db"):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для подключения к БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        """Инициализация базы данных"""
        with self.get_connection() as conn:
            # Таблица отслеживаемых предметов
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tracked_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    min_float REAL NOT NULL,
                    max_float REAL NOT NULL,
                    item_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_check TEXT,
                    last_update TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    total_found INTEGER DEFAULT 0,
                    last_found_count INTEGER DEFAULT 0,
                    settings TEXT DEFAULT '{}',
                    UNIQUE(chat_id, url, min_float, max_float)
                )
            """)
            
            # Таблица найденных предметов
            conn.execute("""
                CREATE TABLE IF NOT EXISTS found_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tracked_item_id INTEGER NOT NULL,
                    item_id TEXT NOT NULL,
                    float_value REAL NOT NULL,
                    price TEXT,
                    condition TEXT,
                    url TEXT,
                    found_at TEXT NOT NULL,
                    is_notified BOOLEAN DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (tracked_item_id) REFERENCES tracked_items(id) ON DELETE CASCADE,
                    UNIQUE(tracked_item_id, item_id)
                )
            """)
            
            # Создаем индексы
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracked_chat ON tracked_items(chat_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracked_active ON tracked_items(is_active)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_found_tracked ON found_items(tracked_item_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_found_notified ON found_items(is_notified)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_found_active ON found_items(is_active)")
            
            # Таблица статистики
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    date TEXT NOT NULL,
                    checks_count INTEGER DEFAULT 0,
                    items_found INTEGER DEFAULT 0,
                    notifications_sent INTEGER DEFAULT 0
                )
            """)
    
    # === Методы для tracked_items ===
    
    def add_tracked_item(self, item: TrackedItem) -> Optional[int]:
        """Добавить отслеживаемый предмет"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Проверяем лимит предметов
                cursor.execute(
                    "SELECT COUNT(*) FROM tracked_items WHERE chat_id = ? AND is_active = 1",
                    (item.chat_id,)
                )
                count = cursor.fetchone()[0]
                
                if count >= 20:  # Лимит предметов
                    return None
                
                # Проверяем, существует ли уже такой предмет
                cursor.execute("""
                    SELECT id FROM tracked_items 
                    WHERE chat_id = ? AND url = ? AND min_float = ? AND max_float = ? AND is_active = 1
                """, (item.chat_id, item.url, item.min_float, item.max_float))
                
                existing = cursor.fetchone()
                if existing:
                    return existing['id']
                
                # Добавляем новый предмет
                cursor.execute("""
                    INSERT INTO tracked_items 
                    (chat_id, url, min_float, max_float, item_name, created_at, last_update, settings)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.chat_id, item.url, item.min_float, item.max_float,
                    item.item_name, item.created_at, item.last_update,
                    json.dumps(item.settings)
                ))
                
                return cursor.lastrowid
                
        except Exception as e:
            logger.error(f"Ошибка добавления предмета: {e}")
            return None
    
    def get_tracked_items(self, chat_id: Optional[int] = None) -> List[TrackedItem]:
        """Получить отслеживаемые предметы"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if chat_id is not None:
                    cursor.execute("""
                        SELECT * FROM tracked_items 
                        WHERE chat_id = ? AND is_active = 1 
                        ORDER BY created_at DESC
                    """, (chat_id,))
                else:
                    cursor.execute("""
                        SELECT * FROM tracked_items 
                        WHERE is_active = 1 
                        ORDER BY created_at DESC
                    """)
                
                items = []
                for row in cursor.fetchall():
                    item = TrackedItem(
                        id=row['id'],
                        chat_id=row['chat_id'],
                        url=row['url'],
                        min_float=row['min_float'],
                        max_float=row['max_float'],
                        item_name=row['item_name'],
                        created_at=row['created_at'],
                        last_check=row['last_check'],
                        last_update=row['last_update'],
                        is_active=bool(row['is_active']),
                        total_found=row['total_found'],
                        last_found_count=row['last_found_count'],
                        settings=json.loads(row['settings'] or '{}')
                    )
                    items.append(item)
                
                return items
                
        except Exception as e:
            logger.error(f"Ошибка получения предметов: {e}")
            return []
    
    def get_tracked_item(self, item_id: int, chat_id: Optional[int] = None) -> Optional[TrackedItem]:
        """Получить конкретный отслеживаемый предмет"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if chat_id is not None:
                    cursor.execute("""
                        SELECT * FROM tracked_items 
                        WHERE id = ? AND chat_id = ? AND is_active = 1
                    """, (item_id, chat_id))
                else:
                    cursor.execute("""
                        SELECT * FROM tracked_items 
                        WHERE id = ? AND is_active = 1
                    """, (item_id,))
                
                row = cursor.fetchone()
                if row:
                    return TrackedItem(
                        id=row['id'],
                        chat_id=row['chat_id'],
                        url=row['url'],
                        min_float=row['min_float'],
                        max_float=row['max_float'],
                        item_name=row['item_name'],
                        created_at=row['created_at'],
                        last_check=row['last_check'],
                        last_update=row['last_update'],
                        is_active=bool(row['is_active']),
                        total_found=row['total_found'],
                        last_found_count=row['last_found_count'],
                        settings=json.loads(row['settings'] or '{}')
                    )
                return None
                
        except Exception as e:
            logger.error(f"Ошибка получения предмета: {e}")
            return None
    
    def update_tracked_item(self, item: TrackedItem) -> bool:
        """Обновить отслеживаемый предмет"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE tracked_items 
                    SET last_check = ?, last_update = ?, total_found = ?, 
                        last_found_count = ?, settings = ?
                    WHERE id = ?
                """, (
                    item.last_check or datetime.now().isoformat(),
                    datetime.now().isoformat(),
                    item.total_found,
                    item.last_found_count,
                    json.dumps(item.settings),
                    item.id
                ))
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Ошибка обновления предмета: {e}")
            return False
    
    def delete_tracked_item(self, item_id: int, chat_id: Optional[int] = None) -> bool:
        """Удалить отслеживаемый предмет"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if chat_id is not None:
                    cursor.execute("""
                        DELETE FROM tracked_items 
                        WHERE id = ? AND chat_id = ?
                    """, (item_id, chat_id))
                else:
                    cursor.execute("DELETE FROM tracked_items WHERE id = ?", (item_id,))
                
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Ошибка удаления предмета: {e}")
            return False
    
    # === Методы для found_items ===
    
    def add_found_item(self, found_item: FoundItem) -> bool:
        """Добавить найденный предмет"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Проверяем, существует ли уже
                cursor.execute("""
                    SELECT id FROM found_items 
                    WHERE tracked_item_id = ? AND item_id = ?
                """, (found_item.tracked_item_id, found_item.item_id))
                
                if cursor.fetchone():
                    return False  # Уже существует
                
                # Добавляем новый
                cursor.execute("""
                    INSERT INTO found_items 
                    (tracked_item_id, item_id, float_value, price, condition, url, found_at, is_notified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    found_item.tracked_item_id, found_item.item_id,
                    found_item.float_value, found_item.price, found_item.condition,
                    found_item.url, found_item.found_at, found_item.is_notified
                ))
                
                # Обновляем счетчик в tracked_items
                cursor.execute("""
                    UPDATE tracked_items 
                    SET total_found = total_found + 1,
                        last_found_count = last_found_count + 1,
                        last_update = ?
                    WHERE id = ?
                """, (datetime.now().isoformat(), found_item.tracked_item_id))
                
                return True
                
        except Exception as e:
            logger.error(f"Ошибка добавления найденного предмета: {e}")
            return False
    
    def get_found_items(self, tracked_item_id: int, limit: int = 50, 
                        only_new: bool = False) -> List[FoundItem]:
        """Получить найденные предметы"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                    SELECT * FROM found_items 
                    WHERE tracked_item_id = ? AND is_active = 1
                """
                params = [tracked_item_id]
                
                if only_new:
                    query += " AND is_notified = 0"
                
                query += " ORDER BY found_at DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                
                items = []
                for row in cursor.fetchall():
                    item = FoundItem(
                        id=row['id'],
                        tracked_item_id=row['tracked_item_id'],
                        item_id=row['item_id'],
                        float_value=row['float_value'],
                        price=row['price'],
                        condition=row['condition'],
                        url=row['url'],
                        found_at=row['found_at'],
                        is_notified=bool(row['is_notified']),
                        is_active=bool(row['is_active'])
                    )
                    items.append(item)
                
                return items
                
        except Exception as e:
            logger.error(f"Ошибка получения найденных предметов: {e}")
            return []
    
    def mark_as_notified(self, found_item_ids: List[int]) -> bool:
        """Пометить предметы как уведомленные"""
        if not found_item_ids:
            return True
            
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ','.join(['?'] * len(found_item_ids))
                cursor.execute(f"""
                    UPDATE found_items 
                    SET is_notified = 1 
                    WHERE id IN ({placeholders})
                """, found_item_ids)
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Ошибка пометки как уведомленные: {e}")
            return False
    
    def clear_old_found_items(self, days: int = 7) -> int:
        """Очистить старые найденные предметы"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
                cursor.execute("""
                    DELETE FROM found_items 
                    WHERE found_at < ? AND is_notified = 1
                """, (cutoff_date,))
                return cursor.rowcount
                
        except Exception as e:
            logger.error(f"Ошибка очистки старых предметов: {e}")
            return 0
    
    # === Методы для статистики ===
    
    def get_stats(self, chat_id: Optional[int] = None) -> Dict[str, Any]:
        """Получить статистику"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                stats = {}
                
                if chat_id is not None:
                    # Статистика для конкретного пользователя
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total_items,
                            SUM(total_found) as total_found,
                            MAX(last_update) as last_update
                        FROM tracked_items 
                        WHERE chat_id = ? AND is_active = 1
                    """, (chat_id,))
                    
                    row = cursor.fetchone()
                    if row:
                        stats.update({
                            'total_items': row['total_items'] or 0,
                            'total_found': row['total_found'] or 0,
                            'last_update': row['last_update']
                        })
                    
                    # Предметы с найденными лотами
                    cursor.execute("""
                        SELECT item_name, total_found 
                        FROM tracked_items 
                        WHERE chat_id = ? AND is_active = 1 AND total_found > 0
                        ORDER BY total_found DESC 
                        LIMIT 5
                    """, (chat_id,))
                    
                    top_items = []
                    for row in cursor.fetchall():
                        top_items.append({
                            'name': row['item_name'],
                            'found': row['total_found']
                        })
                    
                    stats['top_items'] = top_items
                    
                else:
                    # Общая статистика
                    cursor.execute("SELECT COUNT(*) as total FROM tracked_items WHERE is_active = 1")
                    stats['total_tracked'] = cursor.fetchone()['total'] or 0
                    
                    cursor.execute("SELECT COUNT(*) as total FROM found_items WHERE is_active = 1")
                    stats['total_found'] = cursor.fetchone()['total'] or 0
                
                return stats
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}
    
    def update_stats(self, chat_id: int, checks: int = 0, 
                    found: int = 0, notified: int = 0) -> bool:
        """Обновить статистику"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                today = datetime.now().strftime("%Y-%m-%d")
                
                # Проверяем, есть ли запись на сегодня
                cursor.execute("""
                    SELECT id FROM stats 
                    WHERE chat_id = ? AND date = ?
                """, (chat_id, today))
                
                if cursor.fetchone():
                    # Обновляем существующую
                    cursor.execute("""
                        UPDATE stats 
                        SET checks_count = checks_count + ?,
                            items_found = items_found + ?,
                            notifications_sent = notifications_sent + ?
                        WHERE chat_id = ? AND date = ?
                    """, (checks, found, notified, chat_id, today))
                else:
                    # Создаем новую
                    cursor.execute("""
                        INSERT INTO stats (chat_id, date, checks_count, items_found, notifications_sent)
                        VALUES (?, ?, ?, ?, ?)
                    """, (chat_id, today, checks, found, notified))
                
                return True
                
        except Exception as e:
            logger.error(f"Ошибка обновления статистики: {e}")
            return False
    
    def get_user_stats_history(self, chat_id: int, days: int = 7) -> List[Dict]:
        """Получить историю статистики пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                
                cursor.execute("""
                    SELECT date, checks_count, items_found, notifications_sent
                    FROM stats 
                    WHERE chat_id = ? AND date >= ?
                    ORDER BY date DESC
                """, (chat_id, start_date))
                
                history = []
                for row in cursor.fetchall():
                    history.append({
                        'date': row['date'],
                        'checks': row['checks_count'],
                        'found': row['items_found'],
                        'notified': row['notifications_sent']
                    })
                
                return history
                
        except Exception as e:
            logger.error(f"Ошибка получения истории: {e}")
            return []