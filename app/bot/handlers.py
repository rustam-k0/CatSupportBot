import re
import logging
from telegram import Update
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler, filters,
    ConversationHandler, CallbackQueryHandler
)

from app.services.vision_ocr import recognize_text
from app.services.data_parser import parse_date, parse_amount, parse_bank, parse_author
from app.services.sheets_client import write_transaction
from app.bot.keyboards import get_transaction_type_keyboard, get_confirmation_keyboard, get_editing_keyboard

logger = logging.getLogger(__name__)

# --- Определяем состояния диалога ---
(
    AWAITING_TYPE, AWAITING_PET, AWAITING_PHOTO,
    CONFIRMATION, EDITING, AWAITING_EDIT_VALUE,
    AWAITING_COMMENT
) = range(7)

# --- Вспомогательные функции ---

def build_summary_text(data: dict) -> str:
    """Формирует текст-сводку по текущим данным."""
    ud = data
    type_str = '✅ Приход' if ud.get('type') == 'income' else '❌ Расход'
    
    summary_parts = [
        f"Тип: *{type_str}*",
        f"Питомец: *{ud.get('pet_name', 'не указан')}*",
        f"Дата: *{ud.get('date', 'не указана')}*",
        f"Сумма: *{ud.get('amount', 'не указана')}*",
        f"Автор: *{ud.get('author', 'не указан')}*",
    ]
    if ud.get('type') == 'income':
        summary_parts.append(f"Банк: *{ud.get('bank', 'не указан')}*")

    return "\n".join(summary_parts)

async def _end_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> int:
    """Универсальная функция для завершения диалога."""
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text=message)
        else:
            await update.message.reply_text(text=message)
    except Exception as e:
        logger.error(f"Ошибка при завершении диалога: {e}")
    
    context.user_data.clear()
    return ConversationHandler.END

async def _safe_edit_message(update: Update, text: str, reply_markup=None):
    """Безопасное редактирование сообщения с обработкой ошибок."""
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения: {e}")

# --- Обработчики диалога ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа или перезапуск диалога."""
    context.user_data.clear()
    text = "Привет! Начнем запись. Это приход или расход?"
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=get_transaction_type_keyboard())
        else:
            await update.message.reply_text(text, reply_markup=get_transaction_type_keyboard())
        return AWAITING_TYPE
    except Exception as e:
        logger.error(f"Ошибка в start: {e}")
        await _end_conversation(update, context, "Произошла ошибка. Попробуйте снова /start")
        return ConversationHandler.END

async def handle_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора типа операции."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'action_cancel':
        return await _end_conversation(update, context, "Действие отменено.")
        
    try:
        context.user_data['type'] = query.data.split('_')[1] # 'income' or 'expense'
        await query.edit_message_text(text="Отлично. Теперь введите имя питомца (проекта):")
        return AWAITING_PET
    except Exception as e:
        logger.error(f"Ошибка в handle_type: {e}")
        await _end_conversation(update, context, "Ошибка выбора типа. Попробуйте снова /start")
        return ConversationHandler.END

async def handle_pet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода имени питомца."""
    try:
        context.user_data['pet_name'] = update.message.text.strip()
        if not context.user_data['pet_name']:
            await update.message.reply_text("Имя питомца не может быть пустым. Введите имя:")
            return AWAITING_PET
            
        await update.message.reply_text("Имя принято. Теперь отправьте фото чека или скриншот операции.")
        return AWAITING_PHOTO
    except Exception as e:
        logger.error(f"Ошибка в handle_pet: {e}")
        await update.message.reply_text("Ошибка обработки имени. Попробуйте снова.")
        return AWAITING_PET

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает фото, распознает данные и выводит на подтверждение."""
    try:
        await update.message.reply_text("Фото получил, распознаю... 🧐")
        
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        recognized_text = await recognize_text(image_bytes)
        
        # Проверяем, что распознавание прошло успешно
        if recognized_text is None or recognized_text.startswith(('Ошибка', 'КЛИЕНТ', 'Доступ запрещен')):
            error_msg = "❌ Не удалось распознать текст. "
            if recognized_text:
                error_msg += f"Причина: {recognized_text}"
            else:
                error_msg += "Пожалуйста, отправьте более четкое изображение."
            
            await update.message.reply_text(error_msg)
            return AWAITING_PHOTO

        logger.info(f"Распознанный текст: {recognized_text[:200]}...")

        # Парсим все возможные данные
        context.user_data['date'] = parse_date(recognized_text)
        context.user_data['amount'] = parse_amount(recognized_text)
        context.user_data['bank'] = parse_bank(recognized_text)
        context.user_data['author'] = parse_author(recognized_text)
        
        # Проверяем минимально необходимые данные
        if not context.user_data.get('amount'):
            await update.message.reply_text(
                "❌ Не удалось автоматически извлечь сумму. "
                "Вы можете ввести её вручную на следующем шаге."
            )

        summary_text = build_summary_text(context.user_data)
        await update.message.reply_text(
            f"Вот что удалось распознать:\n\n{summary_text}",
            reply_markup=get_confirmation_keyboard(), 
            parse_mode='Markdown'
        )
        return CONFIRMATION
        
    except Exception as e:
        logger.error(f"Ошибка в handle_photo: {e}")
        await update.message.reply_text("❌ Ошибка обработки фото. Попробуйте отправить еще раз.")
        return AWAITING_PHOTO

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка кнопок подтверждения."""
    query = update.callback_query
    await query.answer()

    action = query.data
    try:
        if action == 'confirm_save':
            await query.edit_message_text("Отлично! Введите комментарий или /skip, если его нет.")
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
    except Exception as e:
        logger.error(f"Ошибка в handle_confirmation: {e}")
        await _end_conversation(update, context, "Ошибка подтверждения. Попробуйте снова /start")
        return ConversationHandler.END

async def handle_edit_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора поля для редактирования."""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == 'edit_back':
            summary_text = build_summary_text(context.user_data)
            await query.edit_message_text(
                f"Проверьте данные:\n\n{summary_text}",
                reply_markup=get_confirmation_keyboard(),
                parse_mode='Markdown'
            )
            return CONFIRMATION

        field_to_edit = query.data.split('_', 1)[1]
        context.user_data['field_to_edit'] = field_to_edit
        
        field_map = {
            'pet_name': 'имя питомца', 
            'date': 'дату (в формате ДД.ММ.ГГГГ)',
            'amount': 'сумму (число, например: 1500.50)', 
            'bank': 'название банка', 
            'author': 'автора'
        }
        
        await query.edit_message_text(
            f"Введите новое значение для поля '{field_map.get(field_to_edit, 'поле')}':"
        )
        return AWAITING_EDIT_VALUE
    except Exception as e:
        logger.error(f"Ошибка в handle_edit_selection: {e}")
        await _safe_edit_message(update, "Ошибка выбора поля. Попробуйте снова.")
        return EDITING

async def handle_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка нового значения для поля."""
    try:
        field = context.user_data.pop('field_to_edit', None)
        if not field: 
            return CONFIRMATION
        
        new_value = update.message.text.strip()
        
        # Валидация в зависимости от поля
        if field == 'amount':
            try:
                # Нормализуем и преобразуем сумму
                normalized = new_value.replace(' ', '').replace(',', '.')
                new_value = float(normalized)
                if new_value <= 0:
                    await update.message.reply_text("Сумма должна быть положительной. Введите снова:")
                    context.user_data['field_to_edit'] = field
                    return AWAITING_EDIT_VALUE
            except ValueError:
                await update.message.reply_text("Неверный формат суммы. Введите число (например: 1500.50):")
                context.user_data['field_to_edit'] = field
                return AWAITING_EDIT_VALUE
                
        elif field == 'date':
            # Простая валидация даты
            if not re.match(r'\d{2}\.\d{2}\.\d{4}', new_value):
                await update.message.reply_text("Неверный формат даты. Используйте ДД.ММ.ГГГГ:")
                context.user_data['field_to_edit'] = field
                return AWAITING_EDIT_VALUE
        
        context.user_data[field] = new_value
        summary_text = build_summary_text(context.user_data)
        
        await update.message.reply_text(
            f"Данные обновлены. Проверьте еще раз:\n\n{summary_text}",
            reply_markup=get_confirmation_keyboard(), 
            parse_mode='Markdown'
        )
        return CONFIRMATION
        
    except Exception as e:
        logger.error(f"Ошибка в handle_new_value: {e}")
        await update.message.reply_text("Ошибка обновления значения. Попробуйте снова.")
        return AWAITING_EDIT_VALUE
    
async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE, skip: bool = False) -> int:
    """Обработка комментария и финальное сохранение."""
    message_to_reply = update.message
    
    try:
        if skip:
            context.user_data['comment'] = ''
            await message_to_reply.reply_text("Сохраняю запись без комментария...")
        else:
            context.user_data['comment'] = message_to_reply.text
            await message_to_reply.reply_text("Комментарий принят. Сохраняю запись...")
        
        # Валидация обязательных полей
        required_fields = ['pet_name', 'amount', 'date']
        missing_fields = [field for field in required_fields if not context.user_data.get(field)]
        
        if missing_fields:
            error_msg = f"Не заполнены обязательные поля: {', '.join(missing_fields)}. Начните заново /start"
            await message_to_reply.reply_text(error_msg)
            return await _end_conversation(update, context, "Ошибка валидации данных")
        
        # Сохраняем в Google Sheets
        link = write_transaction(context.user_data['pet_name'], context.user_data)
        
        if link:
            final_message = f"✅ Запись успешно сохранена!\n\nСсылка на таблицу: [открыть]({link})"
        else:
            final_message = "❌ Ошибка! Не удалось сохранить запись. Проверьте настройки таблицы."
            
        await message_to_reply.reply_text(
            final_message, 
            parse_mode='Markdown', 
            disable_web_page_preview=True
        )
        return await _end_conversation(update, context, "Операция завершена.")
        
    except Exception as e:
        logger.error(f"Ошибка в handle_comment: {e}")
        await message_to_reply.reply_text("❌ Ошибка при сохранении. Попробуйте снова /start")
        return await _end_conversation(update, context, "Ошибка сохранения")
    
async def get_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_comment(update, context, skip=False)
    
async def skip_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_comment(update, context, skip=True)
    
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет инструкцию по использованию."""
    help_text = """
📖 *Инструкция по использованию бота:*

1. */start* - начать новую запись
2. */help* - показать эту справку  
3. */cancel* - отменить текущую операцию

*Процесс записи:*
- Выберите тип операции (приход/расход)
- Введите имя питомца или проекта
- Отправьте фото чека или скриншот
- Проверьте распознанные данные
- При необходимости исправьте поля
- Добавьте комментарий (опционально)
- Данные сохранятся в Google таблицу

Для отмены в любой момент используйте /cancel
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды отмены."""
    return await _end_conversation(update, context, "Действие отменено.")

# Создаем обработчики для main.py
start_handler = CommandHandler("start", start)
help_handler = CommandHandler("help", help_command)
cancel_handler = CommandHandler("cancel", cancel)

# Основной обработчик диалога
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        AWAITING_TYPE: [CallbackQueryHandler(handle_type)],
        AWAITING_PET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pet)],
        AWAITING_PHOTO: [MessageHandler(filters.PHOTO, handle_photo)],
        CONFIRMATION: [CallbackQueryHandler(handle_confirmation)],
        EDITING: [CallbackQueryHandler(handle_edit_selection)],
        AWAITING_EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_value)],
        AWAITING_COMMENT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_comment),
            CommandHandler("skip", skip_comment),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)