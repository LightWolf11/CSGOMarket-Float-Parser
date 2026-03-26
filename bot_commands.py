import logging
import pytz
from datetime import datetime
from typing import Dict, List, Tuple, Set
import aiohttp
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from config import TELEGRAM_BOT_TOKEN

# ================== КОНФИГУРАЦИЯ ==================
TOKEN = TELEGRAM_BOT_TOKEN

# Указываем временную зону явно
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# =============== ГЛОБАЛЬНЫЕ СТРУКТУРЫ ДАННЫХ ===============
user_trackings: Dict[int, Dict[str, List[Tuple[float, float]]]] = {}
processed_items: Dict[int, Set[str]] = {}

# ================== КОМАНДЫ БОТА ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для отслеживания скинов CS:GO с определенным float значением.\n\n"
        "📋 **Доступные команды:**\n"
        "/track [ссылка] [мин_флот] [макс_флот] - Добавить отслеживание\n"
        "/list - Показать все отслеживания\n"
        "/delete [номер] - Удалить отслеживание\n"
        "/check - Проверить сейчас\n"
        "/clear - Удалить всё\n\n"
        "Пример:\n"
        "/track https://market.csgo.com/... 0.15 0.18"
    )

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 3:
        await update.message.reply_text(
            "❌ Неправильный формат команды.\n"
            "✅ Используйте: /track [ссылка] [мин_флот] [макс_флот]\n\n"
            "Пример:\n"
            "/track https://market.csgo.com/ru/Rifle/M4A1-S/M4A1-S%20%7C%20Black%20Lotus%20(Field-Tested) 0.15 0.18"
        )
        return
    
    url = context.args[0]
    
    if not url.startswith('https://market.csgo.com/'):
        await update.message.reply_text("❌ Неверная ссылка. Используйте ссылки только с market.csgo.com")
        return
    
    try:
        min_float = float(context.args[1])
        max_float = float(context.args[2])
    except ValueError:
        await update.message.reply_text("❌ Неверные значения float. Используйте числа (например: 0.15 0.18)")
        return
    
    if min_float < 0 or max_float > 1 or min_float > max_float:
        await update.message.reply_text(
            "❌ Неверный диапазон float. Допустимые значения: 0.0 - 1.0\n"
            "Минимальное значение должно быть меньше максимального."
        )
        return
    
    user_id = update.effective_user.id
    
    if user_id not in user_trackings:
        user_trackings[user_id] = {}
        processed_items[user_id] = set()
    
    if url not in user_trackings[user_id]:
        user_trackings[user_id][url] = []
    
    user_trackings[user_id][url].append((min_float, max_float))
    
    await update.message.reply_text(
        f"✅ Отслеживание добавлено!\n\n"
        f"📄 Страница: {url[:50]}...\n"
        f"🎯 Диапазон float: {min_float:.4f} - {max_float:.4f}\n\n"
        f"🔄 Для проверки используйте команду /check"
    )

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_trackings or not user_trackings[user_id]:
        await update.message.reply_text("📭 У вас нет активных отслеживаний.")
        return
    
    message_lines = ["📋 **Ваши отслеживания:**\n"]
    
    for i, (url, ranges) in enumerate(user_trackings[user_id].items(), 1):
        message_lines.append(f"\n{i}. {url[:60]}...")
        for j, (min_float, max_float) in enumerate(ranges, 1):
            message_lines.append(f"   {j}) Float: {min_float:.4f} - {max_float:.4f}")
    
    message_lines.append("\n🗑️ Для удаления используйте /delete [номер]")
    
    full_message = "\n".join(message_lines)
    await update.message.reply_text(full_message, parse_mode='Markdown')

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_trackings or not user_trackings[user_id]:
        await update.message.reply_text("📭 Нет активных отслеживаний для проверки.")
        return
    
    await update.message.reply_text("🔄 Начинаю проверку всех страниц...")
    
    # Здесь будет логика проверки страниц
    found_items = 0
    
    # Имитация проверки
    for url, ranges in user_trackings[user_id].items():
        for min_float, max_float in ranges:
            # TODO: Реализовать реальную проверку через aiohttp + BeautifulSoup
            pass
    
    if found_items > 0:
        await update.message.reply_text(f"✅ Найдено {found_items} подходящих предметов!")
    else:
        await update.message.reply_text("ℹ️ Подходящих предметов не найдено.")

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_trackings or not user_trackings[user_id]:
        await update.message.reply_text("📭 Нет активных отслеживаний для удаления.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажите номер отслеживания: /delete [номер]")
        return
    
    try:
        item_num = int(context.args[0])
        items = list(user_trackings[user_id].keys())
        
        if 1 <= item_num <= len(items):
            url_to_delete = items[item_num - 1]
            del user_trackings[user_id][url_to_delete]
            
            await update.message.reply_text(
                f"✅ Отслеживание #{item_num} удалено.\n"
                f"Страница: {url_to_delete[:50]}..."
            )
        else:
            await update.message.reply_text(f"❌ Нет отслеживания с номером {item_num}.")
            
    except ValueError:
        await update.message.reply_text("❌ Используйте номер отслеживания (например: /delete 1)")

async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id in user_trackings:
        user_trackings[user_id].clear()
        processed_items[user_id].clear()
        await update.message.reply_text("✅ Все отслеживания удалены.")
    else:
        await update.message.reply_text("📭 Нет активных отслеживаний.")

# ================== ЗАПУСК БОТА ==================

def main() -> None:
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    # Создание приложения с явным указанием параметров
    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )
    
    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("track", track))
    application.add_handler(CommandHandler("list", list_cmd))
    application.add_handler(CommandHandler("delete", delete_cmd))
    application.add_handler(CommandHandler("check", check_now))
    application.add_handler(CommandHandler("clear", clear_cmd))
    
    print("✅ Бот запущен!")
    print("📝 Используйте команду /start для начала работы")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()