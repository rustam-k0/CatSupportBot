# app/bot/handlers.py

import re
import logging
from telegram import Update
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler, filters,
    ConversationHandler, CallbackQueryHandler
)
# Импортируем сервисы и клавиатуры
from app.services.vision_ocr import recognize_text
from app.services.data_parser import parse_date, parse_amount, parse_bank, parse_author
from app.services.sheets_client import write_transaction
from app.bot.keyboards import get_transaction_type_keyboard, get_confirmation_keyboard, get_editing_keyboard

# Настройка логирования
logger = logging.getLogger(__name__)

# Определяем состояния диалога в виде констант для лучшей читаемости
(
    AWAITING_TYPE, AWAITING_PET, AWAITING_PHOTO,
    CONFIRMATION, EDITING, AWAITING_EDIT_VALUE,
    AWAITING_COMMENT
) = range(7)

# --- Вспомогательные функции ---

def build_summary_text(data: dict) -> str:
    """Формирует текст-сводку по текущим данным транзакции."""
    ud = data
    type_str = '✅ Приход (донат)' if ud.get('type') == 'income' else '❌ Расход (покупка)'

    # Собираем части сообщения, исключая пустые значения для чистоты вывода
    summary_parts = [
        f"Тип: *{type_str}*",
        f"Питомец/Проект: *{ud.get('pet_name', 'не указан')}*",
        f"Дата: *{ud.get('date', 'не указана')}*",
        f"Сумма: *{ud.get('amount', 'не указана')}*",
        # Изменение здесь: более универсальное название поля
        f"Автор/Источник: *{ud.get('author', 'не указан')}*",
    ]
    if ud.get('type') == 'income':
        summary_parts.append(f"Банк: *{ud.get('bank', 'не указан')}*")

    return "\n".join(summary_parts)

async def _end_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> int:
    """
    Корректно завершает диалог, отправляя финальное сообщение.
    Очищает данные пользователя, чтобы избежать их утечки в следующий диалог.
    """
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text=message)
        else:
            await update.message.reply_text(text=message)
    except Exception as e:
        logger.error(f"Ошибка при отправке финального сообщения в диалоге: {e}")

    context.user_data.clear()
    return ConversationHandler.END

# --- Обработчики состояний диалога (без изменений) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает или перезапускает диалог, очищая предыдущее состояние."""
    context.user_data.clear()
    text = "Привет! Начнем запись. Это приход или расход?"

    reply_markup = get_transaction_type_keyboard()
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

    return AWAITING_TYPE

async def handle_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор типа операции (приход/расход)."""
    query = update.callback_query
    await query.answer()

    if query.data == 'action_cancel':
        return await _end_conversation(update, context, "Действие отменено.")

    context.user_data['type'] = query.data.split('_')[1]
    await query.edit_message_text(text="Отлично. Теперь введите имя питомца или название проекта:")
    return AWAITING_PET

async def handle_pet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает имя питомца/проекта."""
    pet_name = update.message.text.strip()
    if not pet_name:
        await update.message.reply_text("Имя не может быть пустым. Пожалуйста, введите имя питомца:")
        return AWAITING_PET

    context.user_data['pet_name'] = pet_name
    await update.message.reply_text("Имя принято. Теперь отправьте фото чека или скриншот операции.")
    return AWAITING_PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает фото, запускает OCR и парсинг, затем предлагает подтвердить данные."""
    await update.message.reply_text("Фото получил, распознаю... 🧐 Это может занять несколько секунд.")

    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        
        recognized_text = await recognize_text(bytes(image_bytes))

        if not recognized_text or recognized_text.startswith("Ошибка"):
            error_msg = f"❌ Не удалось распознать текст. Причина: {recognized_text}. Попробуйте более четкое фото."
            await update.message.reply_text(error_msg)
            return AWAITING_PHOTO

        logger.info(f"Распознанный текст: {recognized_text[:300]}...")

        context.user_data['date'] = parse_date(recognized_text)
        context.user_data['amount'] = parse_amount(recognized_text)
        context.user_data['author'] = parse_author(recognized_text)
        
        if context.user_data.get('type') == 'income':
            context.user_data['bank'] = parse_bank(recognized_text)

        if not context.user_data.get('amount'):
            await update.message.reply_text(
                "⚠️ Не удалось автоматически извлечь сумму. Вы сможете ввести её вручную на следующем шаге."
            )

        summary_text = build_summary_text(context.user_data)
        await update.message.reply_text(
            f"Вот что удалось распознать:\n\n{summary_text}",
            reply_markup=get_confirmation_keyboard(),
            parse_mode='Markdown'
        )
        return CONFIRMATION

    except Exception as e:
        logger.error(f"Критическая ошибка в handle_photo: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла непредвиденная ошибка при обработке фото. Попробуйте еще раз.")
        return AWAITING_PHOTO

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает кнопки на этапе подтверждения."""
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == 'confirm_save':
        # Для расхода комментарий - это назначение, поэтому он важен. Для прихода - опционален.
        comment_prompt = "Введите назначение расхода (например, 'Корм' или 'Прививка')." if context.user_data.get('type') == 'expense' else "Введите комментарий от донатера (по желанию)."
        await query.edit_message_text(f"{comment_prompt}\nЕсли комментария нет, нажмите /skip.")
        return AWAITING_COMMENT

    elif action == 'confirm_edit':
        await query.edit_message_text(
            "Какое поле вы хотите исправить?",
            reply_markup=get_editing_keyboard(context.user_data)
        )
        return EDITING

    elif action == 'action_restart':
        return await start(update, context)

    elif action == 'action_cancel':
        return await _end_conversation(update, context, "Действие отменено.")

    return CONFIRMATION

async def handle_edit_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор поля для редактирования."""
    query = update.callback_query
    await query.answer()

    if query.data == 'edit_back':
        summary_text = build_summary_text(context.user_data)
        await query.edit_message_text(
            f"Проверьте данные еще раз:\n\n{summary_text}",
            reply_markup=get_confirmation_keyboard(),
            parse_mode='Markdown'
        )
        return CONFIRMATION

    field_to_edit = query.data.split('_', 1)[1]
    context.user_data['field_to_edit'] = field_to_edit

    field_map = {
        'pet_name': 'имя питомца',
        'date': 'дату (ДД.ММ.ГГГГ)',
        'amount': 'сумму (число, например: 1500.50)',
        'bank': 'название банка',
        'author': 'автора/источник'
    }

    await query.edit_message_text(f"Введите новое значение для поля '{field_map.get(field_to_edit, 'неизвестное поле')}':")
    return AWAITING_EDIT_VALUE

async def handle_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает новое значение, валидирует его и обновляет данные."""
    field = context.user_data.pop('field_to_edit', None)
    if not field:
        summary_text = build_summary_text(context.user_data)
        await update.message.reply_text(
            f"Что-то пошло не так. Вернемся к проверке:\n\n{summary_text}",
            reply_markup=get_confirmation_keyboard(), parse_mode='Markdown'
        )
        return CONFIRMATION

    new_value = update.message.text.strip()

    if field == 'amount':
        try:
            # Более надежная очистка значения суммы
            normalized_value = re.sub(r'[^\d,.]', '', new_value).replace(',', '.')
            parsed_amount = float(normalized_value)
            if parsed_amount <= 0:
                await update.message.reply_text("Сумма должна быть положительным числом. Попробуйте снова:")
                context.user_data['field_to_edit'] = field
                return AWAITING_EDIT_VALUE
            new_value = parsed_amount
        except (ValueError, TypeError):
            await update.message.reply_text("Неверный формат суммы. Введите число (например: 1500.50):")
            context.user_data['field_to_edit'] = field
            return AWAITING_EDIT_VALUE

    elif field == 'date':
        # Простая проверка формата, основная валидация - в парсере
        if not re.match(r'^\d{2}[./-]\d{2}[./-]\d{2,4}$', new_value):
            await update.message.reply_text("Неверный формат даты. Пожалуйста, используйте ДД.ММ.ГГГГ:")
            context.user_data['field_to_edit'] = field
            return AWAITING_EDIT_VALUE
        # Нормализация даты при ручном вводе
        new_value = new_value.replace('/', '.').replace('-', '.')


    context.user_data[field] = new_value
    summary_text = build_summary_text(context.user_data)

    await update.message.reply_text(
        f"Данные обновлены. Проверьте еще раз:\n\n{summary_text}",
        reply_markup=get_confirmation_keyboard(),
        parse_mode='Markdown'
    )
    return CONFIRMATION

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает введенный комментарий и завершает процесс."""
    context.user_data['comment'] = update.message.text.strip()
    await update.message.reply_text("Комментарий принят. Сохраняю запись...")
    return await save_data(update, context)

async def skip_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Пропускает ввод комментария и завершает процесс."""
    context.user_data['comment'] = ''
    await update.message.reply_text("Сохраняю запись без комментария...")
    return await save_data(update, context)

async def save_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финальный шаг: валидация, сохранение в Google Sheets и завершение диалога."""
    try:
        # Улучшенная проверка на наличие обязательных полей
        required_fields = ['pet_name', 'amount', 'date']
        missing_fields = [field for field in required_fields if not context.user_data.get(field)]

        if missing_fields:
            missing_str = ', '.join(missing_fields)
            error_msg = f"❌ Не удалось сохранить: не заполнены обязательные поля: {missing_str}. Начните заново /start"
            return await _end_conversation(update, context, error_msg)

        logger.info(f"Отправка на запись в Google Sheets: {context.user_data}")
        link = write_transaction(context.user_data)

        if link:
            final_message = f"✅ Запись успешно сохранена!\n\n[Посмотреть запись в таблице]({link})"
        else:
            final_message = "❌ Ошибка! Не удалось сохранить запись. Проверьте логи сервера для деталей."

        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text(
            final_message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"Критическая ошибка в save_data: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла критическая ошибка при сохранении. Попробуйте снова /start")

    context.user_data.clear()
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет инструкцию по использованию бота."""
    help_text = (
        "📖 *Инструкция по использованию бота:*\n\n"
        "1. `/start` - начать новую запись.\n"
        "2. `/help` - показать эту справку.\n"
        "3. `/cancel` - отменить текущую операцию в любой момент.\n\n"
        "*Процесс записи:*\n"
        "- Выберите тип операции (приход/расход).\n"
        "- Введите имя питомца или проекта.\n"
        "- Отправьте фото чека или скриншот.\n"
        "- Проверьте распознанные данные.\n"
        "- При необходимости исправьте поля.\n"
        "- Добавьте комментарий (или пропустите командой /skip).\n"
        "- Данные сохранятся в Google-таблицу."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /cancel, прерывает диалог."""
    return await _end_conversation(update, context, "Действие отменено.")


conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        AWAITING_TYPE: [CallbackQueryHandler(handle_type, pattern='^type_|^action_cancel$')],
        AWAITING_PET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pet)],
        AWAITING_PHOTO: [MessageHandler(filters.PHOTO, handle_photo)],
        CONFIRMATION: [CallbackQueryHandler(handle_confirmation, pattern='^confirm_|^action_')],
        EDITING: [CallbackQueryHandler(handle_edit_selection, pattern='^edit_')],
        AWAITING_EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_value)],
        AWAITING_COMMENT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment),
            CommandHandler("skip", skip_comment),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
)

help_handler = CommandHandler("help", help_command)