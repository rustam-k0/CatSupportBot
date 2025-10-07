from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

# Импортируем нашу новую функцию
from app.services.sheets_client import add_test_record

# Обработчик команды /start (без изменений)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"Привет, {user_name}! 🐾\n\n"
        "Я бот для учета финансов ваших подопечных котиков.\n"
        "Просто отправьте мне фото чека или скриншот доната."
    )

# Обработчик команды /help (без изменений)
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Я умею:\n"
        "1. Принимать фото чеков.\n"
        "2. Распознавать на них текст.\n"
        "3. Сохранять данные в Google-таблицу.\n\n"
        "Отправьте фото, чтобы начать."
    )

# Обработчик для получения фото (ИЗМЕНЕН)
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Фото получил, пробую записать тестовые данные... 📝")
    
    # Вызываем функцию для записи в таблицу
    success = add_test_record()
    
    if success:
        await update.message.reply_text("Успех! Тестовая строка добавлена в вашу Google-таблицу.")
    else:
        await update.message.reply_text("Произошла ошибка при записи в таблицу. Проверьте логи в консоли.")


# Создаем хендлеры
start_handler = CommandHandler("start", start)
help_handler = CommandHandler("help", help_command)
photo_handler = MessageHandler(filters.PHOTO, handle_photo)