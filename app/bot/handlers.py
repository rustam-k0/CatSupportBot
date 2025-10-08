# app/bot/handlers.py

import logging
from telegram import Update
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler, filters,
    ConversationHandler, CallbackQueryHandler
)
from app.services.vision_ocr import recognize_text
from app.services.data_parser import parse_date, parse_amount, parse_bank, parse_author, parse_procedure
from app.services.sheets_client import write_transaction
from app.bot.keyboards import get_transaction_type_keyboard, get_confirmation_keyboard, get_editing_keyboard

logger = logging.getLogger(__name__)

# Определяем состояния диалога
(AWAITING_TYPE, AWAITING_PET, AWAITING_PHOTO, CONFIRMATION, EDITING, AWAITING_EDIT_VALUE, AWAITING_COMMENT) = range(7)

def build_summary_text(data: dict) -> str:
    """Формирует текст-сводку, теперь с полем 'Процедура' для расходов."""
    ud = data
    type_str = '✅ Приход (донат)' if ud.get('type') == 'income' else '❌ Расход (покупка)'

    summary_parts = [
        f"Тип: *{type_str}*",
        f"Питомец/Проект: *{ud.get('pet_name', 'не указан')}*",
        f"Дата: *{ud.get('date', 'не указана')}*",
        f"Сумма: *{ud.get('amount', 'не указана')}*",
    ]
    
    if ud.get('type') == 'income':
        summary_parts.extend([
            f"Банк: *{ud.get('bank', 'не указан')}*",
            f"Автор (донатер): *{ud.get('author', 'не указан')}*"
        ])
    else: # expense
        summary_parts.extend([
            f"Процедура: *{ud.get('procedure', 'не распознана')}*",
            f"Автор (клиника/магазин): *{ud.get('author', 'не указан')}*"
        ])
    
    if ud.get('comment'):
        summary_parts.append(f"Комментарий: *{ud.get('comment')}*")

    return "\n".join(summary_parts)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог, очищает данные и запрашивает тип операции."""
    context.user_data.clear()
    await update.message.reply_text(
        "Привет! Я помогу учесть финансы. Выберите тип операции:",
        reply_markup=get_transaction_type_keyboard()
    )
    return AWAITING_TYPE

async def handle_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор типа операции и запрашивает имя питомца."""
    query = update.callback_query
    await query.answer()
    context.user_data['type'] = query.data
    await query.edit_message_text(text=f"Тип выбран. Теперь введите имя питомца/проекта:")
    return AWAITING_PET

async def handle_pet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод имени питомца и запрашивает фото."""
    pet_name = update.message.text.strip().capitalize()
    context.user_data['pet_name'] = pet_name
    await update.message.reply_text(f"Отлично, работаем с '{pet_name}'. Теперь отправьте фото чека или скриншот перевода.")
    return AWAITING_PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает фото, распознает текст и выводит сводку для подтверждения."""
    await update.message.reply_text("Фото получил, распознаю... 🧐 Это может занять несколько секунд.")
    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        
        recognized_text = await recognize_text(bytes(image_bytes))
        if not recognized_text or recognized_text.startswith("Ошибка"):
            await update.message.reply_text(f"❌ Не удалось распознать текст. Причина: {recognized_text}.")
            return AWAITING_PHOTO

        logger.info(f"Распознанный текст: {recognized_text[:300]}...")
        
        transaction_type = context.user_data.get('type')
        context.user_data['date'] = parse_date(recognized_text)
        context.user_data['amount'] = parse_amount(recognized_text, transaction_type)
        context.user_data['author'] = parse_author(recognized_text, transaction_type)
        
        if transaction_type == 'income':
            context.user_data['bank'] = parse_bank(recognized_text)
        else: # expense
            context.user_data['procedure'] = parse_procedure(recognized_text)

        summary_text = build_summary_text(context.user_data)
        await update.message.reply_text(
            f"Вот что удалось распознать:\n\n{summary_text}",
            reply_markup=get_confirmation_keyboard(),
            parse_mode='Markdown'
        )
        return CONFIRMATION
    except Exception as e:
        logger.error(f"Критическая ошибка в handle_photo: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла непредвиденная ошибка. Попробуйте еще раз.")
        return AWAITING_PHOTO

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает кнопки на этапе подтверждения (Сохранить, Исправить, Отмена)."""
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == 'save':
        await query.edit_message_text("Сохраняю данные... ⏳")
        link = write_transaction(context.user_data)
        if link:
            await query.edit_message_text(f"✅ Данные успешно сохранены!\n\n[Ссылка на таблицу]({link})", parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Произошла ошибка при сохранении. Попробуйте снова.")
        context.user_data.clear()
        return ConversationHandler.END
    
    elif action == 'edit':
        summary_text = build_summary_text(context.user_data)
        await query.edit_message_text(
            f"Какое поле вы хотите исправить?\n\n{summary_text}",
            reply_markup=get_editing_keyboard(context.user_data),
            parse_mode='Markdown'
        )
        return EDITING

    elif action == 'add_comment':
        await query.edit_message_text("Введите ваш комментарий:")
        return AWAITING_COMMENT

    elif action == 'cancel':
        context.user_data.clear()
        await query.edit_message_text("Операция отменена.")
        return ConversationHandler.END
    
    return CONFIRMATION

async def handle_editing_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор поля для редактирования."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'edit_back':
        summary_text = build_summary_text(context.user_data)
        await query.edit_message_text(
            f"Вот что удалось распознать:\n\n{summary_text}",
            reply_markup=get_confirmation_keyboard(),
            parse_mode='Markdown'
        )
        return CONFIRMATION

    field_to_edit = query.data.replace('edit_', '')
    context.user_data['field_to_edit'] = field_to_edit
    
    field_labels = {
        'pet_name': 'питомца', 'date': 'дату (дд.мм.гггг)', 'amount': 'сумму (число)', 
        'bank': 'банк', 'author': 'автора', 'procedure': 'процедуру'
    }
    await query.edit_message_text(f"Введите новое значение для поля '{field_labels.get(field_to_edit, field_to_edit)}':")
    return AWAITING_EDIT_VALUE

async def handle_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает новое значение для поля и возвращает на этап подтверждения."""
    field = context.user_data.pop('field_to_edit', None)
    if field:
        new_value = update.message.text.strip()
        context.user_data[field] = new_value

    summary_text = build_summary_text(context.user_data)
    await update.message.reply_text(
        f"Данные обновлены. Проверьте еще раз:\n\n{summary_text}",
        reply_markup=get_confirmation_keyboard(),
        parse_mode='Markdown'
    )
    return CONFIRMATION

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавляет комментарий и возвращает на этап подтверждения."""
    context.user_data['comment'] = update.message.text.strip()
    summary_text = build_summary_text(context.user_data)
    await update.message.reply_text(
        f"Комментарий добавлен. Проверьте финальные данные:\n\n{summary_text}",
        reply_markup=get_confirmation_keyboard(),
        parse_mode='Markdown'
    )
    return CONFIRMATION

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет и завершает текущий диалог."""
    context.user_data.clear()
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END

# Отдельный обработчик для команды /help
help_handler = CommandHandler('help', lambda u, c: u.message.reply_text("Отправьте /start, чтобы начать, или отправьте фото, если вы уже в процессе диалога."))

# Создание главного обработчика диалогов
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        AWAITING_TYPE: [CallbackQueryHandler(handle_type, pattern='^(income|expense)$')],
        AWAITING_PET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pet)],
        AWAITING_PHOTO: [MessageHandler(filters.PHOTO, handle_photo)],
        CONFIRMATION: [CallbackQueryHandler(handle_confirmation, pattern='^(save|edit|add_comment|cancel)$')],
        EDITING: [CallbackQueryHandler(handle_editing_choice)],
        AWAITING_EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_value)],
        AWAITING_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment)],
    },
    fallbacks=[CommandHandler('cancel', cancel)]
)