from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"Привет, {user_name}! 🐾\n\n"
        "Я бот для учета финансов ваших подопечных котиков.\n"
        "Просто отправьте мне фото чека или скриншот доната."
    )

# Обработчик команды /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Я умею:\n"
        "1. Принимать фото чеков.\n"
        "2. Распознавать на них текст.\n"
        "3. Сохранять данные в Google-таблицу.\n\n"
        "Отправьте фото, чтобы начать."
    )

# Обработчик для получения фото
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Фото получил, начинаю обработку. 🤖")

# Создаем хендлеры
start_handler = CommandHandler("start", start)
help_handler = CommandHandler("help", help_command)
photo_handler = MessageHandler(filters.PHOTO, handle_photo)