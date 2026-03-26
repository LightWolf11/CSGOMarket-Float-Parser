import os
from datetime import timedelta

# === Telegram Bot ===
TELEGRAM_BOT_TOKEN = "YOUR_TOKEN_HERE"  # Замените на ваш токен бота
TELEGRAM_CHAT_ID = "-00000000000"  # Для отправки ошибок админу

CHECK_INTERVAL_MINUTES = 1      # Интервал проверки в минутах
REQUEST_DELAY = 2               # Задержка между запросами (секунды)
MAX_PRICE_RUB = 100000          # Максимальная цена для уведомлений
NOTIFY_ON_START = True          # Показывать все лоты при добавлении
MAX_ITEMS_PER_USER = 20         # Максимальное количество предметов на пользователя

# === Headers для обхода защиты ===
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# === CSS селекторы для парсинга ===
CSS_SELECTORS = {
    'item_container': 'div.item, div.lot, div.product-item, div.market-item',
    'float_value': 'div.float, span.float-value, div.wear',
    'price': 'div.price, span.price, div.item-price',
    'item_name': 'h1, h2, h3, div.item-name',
    'item_link': 'a[href*="/item/"]',
}

# === Регулярные выражения ===
REGEX_PATTERNS = {
    'float_simple': r'(\d+\.\d{3,4})',
    'float_range': r'(\d+\.\d+)\s*[-–]\s*(\d+\.\d+)',
    'float_with_prefix': r'(?:Float|float|FLT|F|Сх\s*)\s*[:]?\s*(\d+\.\d+)',
    'condition_float': r'(FN|MW|FT|WW|BS)\s+(\d+\.\d+)',
    'price_rub': r'(\d+[\s,]*\d*\.?\d*)\s*(?:руб|₽|RUB|р|P)',
    'item_id': r'/item/(\d+)',
    'market_hash_name': r'/([^/]+)\([^)]+\)\.aspx$',
}

# === Сообщения ===
MESSAGES = {
    'start': (
        "🎮 *CS:GO Market Float Tracker*\n\n"
        "Я отслеживаю предметы на market.csgo.com по заданным диапазонам float.\n\n"
        "📋 *Основные команды:*\n"
        "`/track <ссылка> <min> <max>` - добавить отслеживание (покажет ВСЕ лоты сразу!)\n"
        "`/scan <ссылка> <min> <max>` - разовое сканирование\n"
        "`/list` - ваши предметы\n"
        "`/check [номер]` - проверить сейчас\n"
        "`/remove <номер>` - удалить\n"
        "`/stats` - статистика\n"
        "`/help` - справка\n\n"
        "⚡ *Бот показывает ВСЕ существующие лоты при добавлении!*"
    ),
    
    'help': (
        "🆘 *Помощь по командам*\n\n"
        "*Добавить предмет (с показом всех лотов):*\n"
        "`/track <ссылка> <min_float> <max_float>`\n"
        "Пример: `/track https://market.csgo.com/... 0.15 0.18`\n\n"
        "*Разовое сканирование:*\n"
        "`/scan <ссылка> <min> <max>` - только показывает, не сохраняет\n\n"
        "*Управление предметами:*\n"
        "`/list` - все ваши предметы\n"
        "`/check` - проверить все предметы\n"
        "`/check 2` - проверить предмет №2\n"
        "`/remove 3` - удалить предмет №3\n\n"
        "*Статистика:*\n"
        "`/stats` - ваша статистика\n\n"
        "📌 *Пример ссылки:*\n"
        "`https://market.csgo.com/ru/Rifle/M4A1-S/M4A1-S%20%7C%20Black%20Lotus%20%28Field-Tested%29`"
    ),
    
    'item_added': (
        "✅ *Предмет добавлен!*\n\n"
        "Я буду проверять его каждые {interval} минут и уведомлять о новых лотах.\n\n"
        "⚡ *Сканирую страницу сейчас...*"
    ),
    
    'no_items': (
        "📭 *У вас нет отслеживаемых предметов.*\n\n"
        "Используйте `/track` чтобы добавить первый предмет."
    ),
    
    'limit_reached': (
        "⚠️ *Достигнут лимит!*\n\n"
        "Вы можете отслеживать не более {max_items} предметов.\n"
        "Удалите некоторые предметы командой `/remove`."
    )
}

# === Настройки парсера ===
PARSER_CONFIG = {
    'timeout': 30,
    'max_retries': 3,
    'retry_delay': 5,
    'user_agents': [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    ]
}