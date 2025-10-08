# app/bot/handlers.py

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from app.services.vision_ocr import recognize_text

# ... (функции start и help_command остаются без изменений) ...
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"Привет, {user_name}! 🐾\n\n"
        "Я бот для учета финансов ваших подопечных котиков.\n"
        "Просто отправьте мне фото чека или скриншот доната."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Я умею:\n"
        "1. Принимать фото чеков.\n"
        "2. Распознавать на них текст.\n"
        "3. Сохранять данные в Google-таблицу.\n\n"
        "Отправьте фото, чтобы начать."
    )

# --- ИЗМЕНЕННЫЙ ОБРАБОТЧИК ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает фото, распознает текст и показывает результат или ДЕТАЛЬНУЮ ОШИБКУ."""
    
    await update.message.reply_text("Фото получил, начинаю распознавание... 🧐")

    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()

    recognized_data = await recognize_text(bytes(photo_bytes))

    if recognized_data and 'ОШИБКА' not in recognized_data and 'ОТКАЗАНО В ДОСТУПЕ' not in recognized_data:
        # Успешный сценарий
        await update.message.reply_text(
            "Вот что удалось распознать:\n\n"
            f"```\n{recognized_data}\n```",
            parse_mode='MarkdownV2'
        )
    elif recognized_data:
        # Сценарий, когда сервис вернул текст ошибки
        await update.message.reply_text(
            f"❗️ **Произошла ошибка подключения:**\n\n`{recognized_data}`",
            parse_mode='HTML'
        )
    else:
        # Сценарий, когда текст на фото просто не найден
        await update.message.reply_text(
            "Текст на изображении не найден. Пожалуйста, попробуйте другое фото."
        )

# Создаем хендлеры
start_handler = CommandHandler("start", start)
help_handler = CommandHandler("help", help_command)
photo_handler = MessageHandler(filters.PHOTO, handle_photo)