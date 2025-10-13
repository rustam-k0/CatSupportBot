import logging
import re
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler, filters,
    ConversationHandler, CallbackQueryHandler
)

from app.bot.keyboards import get_transaction_type_keyboard, get_confirmation_keyboard, get_editing_keyboard, get_restart_keyboard
from app.services.vision_ocr import recognize_text
from app.services.data_parser import parse_transaction_data
from app.services.sheets_client import write_transaction
from config.settings import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

(STATE_AWAITING_TYPE, STATE_AWAITING_PET, STATE_AWAITING_PHOTO, STATE_CONFIRMATION,
 STATE_EDITING_CHOICE, STATE_AWAITING_EDIT_VALUE, STATE_AWAITING_COMMENT, STATE_DONE) = range(8)

def build_summary_text(data: dict) -> str:
    ud = data
    if ud.get('type') == 'transaction':
        summary_parts = [
            "Тип: 💸 *Транзакции*",
            f"Подопечный: *{ud.get('pet_name', '...')}*",
            f"Дата: *{ud.get('period', 'не определена')}*",
            f"Банк: *{ud.get('bank', 'не определен')}*",
            f"Общий доход за период: *{ud.get('total_income', 'не определен')}*",
            "\n*Найденные операции:*"
        ]
        transactions = ud.get('transactions', [])
        if not transactions:
            summary_parts.append("_Не найдено ни одной операции._")
        else:
            for i, tx in enumerate(transactions, 1):
                details = [f"{i}. *{tx.get('type', 'Операция')}* от *{tx.get('sender', '...')}*"]
                if tx.get('amount_str'): details.append(f"   Сумма: `{tx.get('amount_str')}`")
                if tx.get('card'): details.append(f"   Карта: {tx.get('card')}")
                if tx.get('tag'): details.append(f"   Тег: {tx.get('tag')}")
                summary_parts.append('\n'.join(details))
        return "\n".join(summary_parts)
    else:
        type_str = '📈 *Доход*' if ud.get('type') == 'income' else '🛍️ *Расход*'
        summary_parts = [f"Тип: {type_str}", f"Подопечный: *{ud.get('pet_name', '...')}*"]
        common_parts = [f"Дата: *{ud.get('date', '...')}*", f"Сумма: *{ud.get('amount', '...')} руб*."]
        if ud.get('type') == 'income':
            summary_parts.extend([*common_parts, f"Банк: *{ud.get('bank', '...')}*", f"Отправитель: *{ud.get('author', '...')}*"])
        else:
            summary_parts.extend([*common_parts, f"Назначение: *{ud.get('procedure', '...')}*", f"Поставщик: *{ud.get('author', '...')}*"])
        if ud.get('comment'): summary_parts.append(f"\nКомментарий: _{ud.get('comment')}_")
        return "\n".join(summary_parts)

async def _show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, text_prefix: str):
    full_text = f"{text_prefix}\n\n{build_summary_text(context.user_data)}"
    keyboard = get_confirmation_keyboard()
    if update.callback_query:
        await update.callback_query.edit_message_text(full_text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await update.message.reply_text(full_text, reply_markup=keyboard, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    welcome_text = (f"Привет, {update.effective_user.first_name}! 🐾 Я помогу вам вести учёт финансов.\n\n"
                    "Давайте начнём! Что вы хотите записать?")
    keyboard = get_transaction_type_keyboard()
    if update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=keyboard, parse_mode='Markdown', disable_web_page_preview=True)
    else:
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode='Markdown', disable_web_page_preview=True)
    return STATE_AWAITING_TYPE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Операция отменена. Для начала используйте /start.")
    return ConversationHandler.END

async def handle_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    context.user_data['type'] = query.data
    await query.edit_message_text(text="Напишите имя подопечного (например, *Мурзик*).", parse_mode='Markdown')
    return STATE_AWAITING_PET

async def handle_pet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['pet_name'] = update.message.text.strip().capitalize()
    await update.message.reply_text(f"Учёт для *{context.user_data['pet_name']}*. Теперь пришлите фото.", parse_mode='Markdown')
    return STATE_AWAITING_PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отличное фото! 🧐 Изучаю...")
    try:
        photo_file = await update.message.photo[-1].get_file()
        recognized_text = await recognize_text(bytes(await photo_file.download_as_bytearray()))
        if not recognized_text or recognized_text.startswith("Ошибка"):
            await update.message.reply_text("Не могу разобрать текст. Попробуйте сделать снимок почётче.")
            return STATE_AWAITING_PHOTO
        context.user_data.update(parse_transaction_data(recognized_text, context.user_data.get('type')))
        await _show_summary(update, context, "Готово! ✨ Вот что мне удалось распознать:")
        return STATE_CONFIRMATION
    except Exception as e:
        logger.error(f"Критическая ошибка в handle_photo: {e}", exc_info=True)
        await update.message.reply_text("Упс, что-то пошло не так. Попробуйте отправить фото ещё раз.")
        return STATE_AWAITING_PHOTO

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    action = query.data; ud = context.user_data

    if action == 'save':
        await query.edit_message_text("Минутку, сохраняю данные... ⏳")
        sheet_link, saved_count = None, 0
        if ud.get('type') == 'transaction':
            base_data = {'pet_name': ud.get('pet_name'), 'date': datetime.now().strftime("%d.%m.%Y"), 'bank': ud.get('bank'), 'type': 'income'}
            for tx in ud.get('transactions', []):
                comment = ', '.join(filter(None, [tx.get('type'), f"карта {tx.get('card')}", f"тег: {tx.get('tag')}"]))
                data_to_write = {**base_data, 'author': tx.get('sender'), 'amount': tx.get('amount'), 'comment': comment}
                if result_link := write_transaction(data_to_write):
                    sheet_link, saved_count = result_link, saved_count + 1
        else:
            if sheet_link := write_transaction(ud): saved_count = 1
        
        if saved_count > 0:
            msg = f"✅ *Успех!* Добавлено записей: *{saved_count}*.\n\n🔗 [Посмотреть в таблице]({sheet_link})"
            await query.edit_message_text(msg, parse_mode='Markdown', disable_web_page_preview=True, reply_markup=get_restart_keyboard())
            return STATE_DONE
        else:
            await query.edit_message_text("❌ Не удалось сохранить данные.", reply_markup=get_restart_keyboard())
            return STATE_DONE

    elif action == 'edit':
        await query.edit_message_text(f"Что именно нужно поправить?\n\n{build_summary_text(ud)}",
                                      reply_markup=get_editing_keyboard(ud), parse_mode='Markdown')
        return STATE_EDITING_CHOICE
    elif action == 'add_comment':
        await query.edit_message_text("Напишите комментарий, который нужно добавить:")
        return STATE_AWAITING_COMMENT
    elif action == 'cancel':
        context.user_data.clear()
        await query.edit_message_text("Операция отменена. /start для новой записи.", )
        return ConversationHandler.END
    return STATE_CONFIRMATION

async def handle_editing_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    if query.data == 'edit_back':
        await _show_summary(update, context, "Хорошо, вернёмся к проверке:")
        return STATE_CONFIRMATION
    field = query.data.replace('edit_', '')
    context.user_data['field_to_edit'] = field
    labels = {'pet_name': 'имя', 'date': 'дату (ДД.ММ.ГГГГ)', 'amount': 'сумму', 'bank': 'банк', 'author': 'отправителя'}
    await query.edit_message_text(f"Введите новое значение для поля *'{labels.get(field, field)}'*:", parse_mode='Markdown')
    return STATE_AWAITING_EDIT_VALUE

async def handle_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    field, new_value = context.user_data.get('field_to_edit'), update.message.text.strip()
    context.user_data[field] = new_value
    await _show_summary(update, context, "Готово, поле обновлено! Проверяем ещё раз:")
    return STATE_CONFIRMATION

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['comment'] = update.message.text.strip()
    await _show_summary(update, context, "Комментарий добавлен! Теперь всё правильно?")
    return STATE_CONFIRMATION

def setup_handlers():
    return ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            STATE_AWAITING_TYPE: [CallbackQueryHandler(handle_type, pattern='^(income|expense|transaction)$')],
            STATE_AWAITING_PET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pet)],
            STATE_AWAITING_PHOTO: [MessageHandler(filters.PHOTO, handle_photo)],
            STATE_CONFIRMATION: [CallbackQueryHandler(handle_confirmation)],
            STATE_EDITING_CHOICE: [CallbackQueryHandler(handle_editing_choice)],
            STATE_AWAITING_EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_value)],
            STATE_AWAITING_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment)],
            STATE_DONE: [CallbackQueryHandler(start, pattern='^restart_flow$')]
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start)]
    ), CommandHandler('help', lambda u, c: u.message.reply_text("Используйте /start или /cancel."))