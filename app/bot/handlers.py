import logging
import re
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler, filters,
    ConversationHandler, CallbackQueryHandler
)

from app.bot.keyboards import (
    get_transaction_type_keyboard, get_confirmation_keyboard,
    get_editing_keyboard, get_restart_keyboard
)
from app.services.vision_ocr import recognize_text
from app.services.data_parser import (
    parse_date, parse_amount, parse_bank, parse_author, parse_procedure,
    parse_transaction_data, parse_multiple_transactions
)
from app.services.sheets_client import write_transaction
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

(
    STATE_AWAITING_TYPE,
    STATE_AWAITING_PET,
    STATE_AWAITING_PHOTO,
    STATE_CONFIRMATION,
    STATE_EDITING_CHOICE,
    STATE_AWAITING_EDIT_VALUE,
    STATE_AWAITING_COMMENT,
    STATE_DONE
) = range(8)

def build_summary_text(data: dict) -> str:
    # New logic for multi-transaction summary
    if 'transactions' in data:
        summaries = []
        pet_name = data.get('pet_name', '...')
        date = data.get('date', '...')
        
        for tx in data['transactions']:
            summary_parts = [
                "Тип: 📈 *Доход*",
                f"Подопечный: *{pet_name}*",
                f"Дата: *{date}*",
                f"Сумма: *{tx.get('amount', '...')} руб*.",
                f"Банк: *{tx.get('bank', '...')}*",
                f"Отправитель: *{tx.get('author', '...')}*"
            ]
            summaries.append("\n".join(summary_parts))
        
        final_summary = "\n\n---\n\n".join(summaries)
        
        if data.get('comment'):
            final_summary += f"\n\n*Общий комментарий:* _{data.get('comment')}_"
            
        return final_summary

    # Original logic for single transaction summary
    ud = data
    type_str = '📈 *Доход*' if ud.get('type') == 'income' else '🛍️ *Расход*' if ud.get('type') == 'expense' else '💸 *Транзакция*'

    summary_parts = [f"Тип: {type_str}"]

    if ud.get('type') in ['income', 'transaction']:
        summary_parts.extend([
            f"Подопечный: *{ud.get('pet_name', '...')}*",
            f"Дата: *{ud.get('date', '...')}*",
            f"Сумма: *{ud.get('amount', '...')} руб*.",
            f"Банк: *{ud.get('bank', '...')}*",
            f"Отправитель: *{ud.get('author', '...')}*"
        ])
    else:
        summary_parts.extend([
            f"Подопечный: *{ud.get('pet_name', '...')}*", 
            f"Дата: *{ud.get('date', '...')}*",
            f"Сумма: *{ud.get('amount', '...')} руб*.",
            f"Назначение: *{ud.get('procedure', '...')}*",
            f"Поставщик: *{ud.get('author', '...')}*"
        ])

    if ud.get('comment'):
        summary_parts.append(f"Комментарий: _{ud.get('comment')}_")

    return "\n".join(summary_parts)

async def _show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, text_prefix: str):
    summary_text = build_summary_text(context.user_data)
    full_text = f"{text_prefix}\n\n{summary_text}"

    query = update.callback_query
    if query:
        await query.edit_message_text(
            full_text, reply_markup=get_confirmation_keyboard(), parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            full_text, reply_markup=get_confirmation_keyboard(), parse_mode='Markdown'
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    query = update.callback_query
    user_name = update.effective_user.first_name

    welcome_text = (
        f"Привет, {user_name}! 🐾 Я помогу вам вести учёт финансов.\n\n"
        "**Как это работает:**\n"
        "1. Выберите тип операции: *Доход*, *Расход* или *Транзакции*.\n"
        "2. Укажите, к какому хвостику относится запись 🐈.\n"
        "3. Отправьте фото чека или скриншот перевода.\n\n"
        f"Я всё распознаю, а вы проверите. Готовые записи попадают в [общую таблицу]({settings.GOOGLE_SHEETS_LINK}).\n\n"
        "Давайте начнём! Что вы хотите записать?"
    )
    keyboard = get_transaction_type_keyboard()

    if query:
        await query.answer()
        await query.edit_message_text(
            welcome_text,
            reply_markup=keyboard,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            welcome_text,
            reply_markup=keyboard,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    return STATE_AWAITING_TYPE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Хорошо, операция отменена. Если передумаете, просто вызовите меня командой /start."
    )
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Чем могу помочь? 😼\n\n"
        "➡️ *Начать новую запись* — отправьте команду /start.\n"
        "➡️ *Прервать операцию* — отправьте /cancel в любой момент.\n\n"
        "Я умею распознавать данные с фото чеков и скриншотов, чтобы вам не пришлось вводить всё вручную."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_invalid_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "Ой, что-то пошло не так. 😵‍💫 Похоже, я ожидал другой формат данных.\n\n"
            "Пожалуйста, попробуйте ещё раз или используйте /cancel для отмены."
        )

async def handle_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['type'] = query.data

    await query.edit_message_text(
        text="Отлично! Теперь напишите, пожалуйста, имя подопечного (например, *Мурзик*) или название проекта.",
        parse_mode='Markdown'
    )
    return STATE_AWAITING_PET

async def handle_pet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pet_name = update.message.text.strip().capitalize()
    context.user_data['pet_name'] = pet_name

    await update.message.reply_text(
        f"Записал! Ведём учёт для *{pet_name}*.\n"
        "А теперь пришлите, пожалуйста, фото чека или скриншот операции. 📸\n"
        "Я постараюсь всё распознать сам!",
        parse_mode='Markdown'
    )
    return STATE_AWAITING_PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отличное фото! 🧐 Дайте мне пару секунд, я его изучу...")

    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        recognized_text = await recognize_text(bytes(image_bytes))

        if not recognized_text or recognized_text.startswith("Ошибка"):
            logger.warning("OCR не смог распознать текст.", extra={'ocr_result': recognized_text})
            await update.message.reply_text(
                "Ой, не могу разобрать текст на фото. 😔 Попробуйте, пожалуйста, сделать снимок почётче или при другом освещении."
            )
            return STATE_AWAITING_PHOTO

        logger.info(f"Распознанный текст (первые 300 символов): {recognized_text[:300]}...")

        ud = context.user_data
        transaction_type = ud.get('type')
        
        if transaction_type == 'transaction':
            transactions = parse_multiple_transactions(recognized_text)
            if not transactions:
                await update.message.reply_text(
                    "К сожалению, не удалось найти транзакций на этом скриншоте. Попробуйте другой или выберите тип 'Доход' для одиночной записи."
                )
                return STATE_AWAITING_PHOTO

            ud['transactions'] = transactions
            ud['date'] = datetime.now().strftime("%d.%m.%Y")
        else:
            ud['date'] = parse_date(recognized_text)
            ud['amount'] = parse_amount(recognized_text, transaction_type)
            ud['author'] = parse_author(recognized_text, transaction_type)

            if transaction_type == 'income':
                ud['bank'] = parse_bank(recognized_text)
            else:
                ud['procedure'] = parse_procedure(recognized_text)

        await _show_summary(update, context, "Готово! ✨ Вот что мне удалось распознать:")
        return STATE_CONFIRMATION

    except Exception as e:
        logger.error(f"Критическая ошибка в handle_photo: {e}", exc_info=True)
        await update.message.reply_text(
            "Упс, что-то пошло не так во время обработки фото. 😵‍💫 Попробуйте, пожалуйста, отправить его ещё раз."
        )
        return STATE_AWAITING_PHOTO

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data
    ud = context.user_data

    if action == 'save':
        await query.edit_message_text("Минутку, сохраняю данные в таблицу... ⏳")
        
        if 'transactions' in ud:
            sheet_link = None
            pet_name = ud.get('pet_name', 'хвостик')
            success_count = 0
            
            for tx_data in ud['transactions']:
                full_transaction_data = {
                    'pet_name': ud.get('pet_name'),
                    'date': ud.get('date'),
                    'type': 'income',
                    'amount': tx_data.get('amount'),
                    'bank': tx_data.get('bank'),
                    'author': tx_data.get('author'),
                    'comment': ud.get('comment', '')
                }
                
                try:
                    sheet_link = write_transaction(full_transaction_data)
                    if sheet_link:
                        success_count += 1
                except Exception as e:
                    logger.error(f"Ошибка при записи в Google Sheets (мульти-транзакция): {e}", exc_info=True)
                    await query.edit_message_text("❌ Ошибка при сохранении одной из записей. Пожалуйста, свяжитесь с администратором.")
                    context.user_data.clear()
                    return ConversationHandler.END

            if sheet_link:
                success_message = (
                    f"✅ *Успех!* Записи ({success_count} шт.) для *{pet_name}* добавлены в таблицу.\n\n"
                    f"🔗 [Посмотреть записи в таблице]({sheet_link})"
                )
                await query.edit_message_text(
                    success_message,
                    parse_mode='Markdown',
                    disable_web_page_preview=True,
                    reply_markup=get_restart_keyboard()
                )
                return STATE_DONE
            else:
                error_text = "❌ Не удалось сохранить данные. Что-то пошло не так с таблицей. Пожалуйста, попробуйте снова."
                await query.edit_message_text(error_text, reply_markup=get_restart_keyboard())

        else: # Existing logic for single transaction
            try:
                sheet_link = write_transaction(context.user_data)
                if sheet_link:
                    pet_name = context.user_data.get('pet_name', 'хвостик')
                    success_message = (
                        f"✅ *Успех!* Запись для *{pet_name}* добавлена в таблицу.\n\n"
                        f"🔗 [Посмотреть запись в таблице]({sheet_link})"
                    )
                    await query.edit_message_text(
                        success_message,
                        parse_mode='Markdown',
                        disable_web_page_preview=True,
                        reply_markup=get_restart_keyboard()
                    )
                    return STATE_DONE
                else:
                    error_text = "❌ Не удалось сохранить данные. Что-то пошло не так с таблицей. Пожалуйста, попробуйте снова."
                    await query.edit_message_text(error_text)

            except Exception as e:
                logger.error(f"Ошибка при записи в Google Sheets: {e}", exc_info=True)
                error_text = "❌ Ошибка при сохранении. Пожалуйста, свяжитесь с администратором."
                await query.edit_message_text(error_text)

        context.user_data.clear()
        return ConversationHandler.END

    elif action == 'edit':
        if 'transactions' in ud:
            await query.edit_message_text(
                "Редактирование для нескольких записей сразу не поддерживается. 😅\n\n"
                "Вы можете сохранить все, что распознано верно, либо отменить операцию и добавить записи по одной через кнопку 'Доход'.",
                reply_markup=get_confirmation_keyboard()
            )
            return STATE_CONFIRMATION

        summary_text = build_summary_text(context.user_data)
        await query.edit_message_text(
            f"Что именно нужно поправить? Выберите поле ниже:\n\n{summary_text}",
            reply_markup=get_editing_keyboard(context.user_data), parse_mode='Markdown'
        )
        return STATE_EDITING_CHOICE

    elif action == 'add_comment':
        prompt_text = "Конечно! Напишите комментарий, который нужно добавить:"
        if 'transactions' in ud:
            prompt_text += "\n\n(Он будет применен ко всем записям на скриншоте)"
        await query.edit_message_text(prompt_text)
        return STATE_AWAITING_COMMENT

    elif action == 'cancel':
        context.user_data.clear()
        await query.edit_message_text("Операция отменена. Чтобы начать заново, отправьте /start.")
        return ConversationHandler.END

    return STATE_CONFIRMATION

async def handle_editing_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == 'edit_back':
        await _show_summary(update, context, "Хорошо, вернёмся к проверке. Всё верно?")
        return STATE_CONFIRMATION

    field_to_edit = query.data.replace('edit_', '')
    context.user_data['field_to_edit'] = field_to_edit

    field_labels = {
        'pet_name': 'имя подопечного', 'date': 'дату (в формате ДД.ММ.ГГГГ)',
        'amount': 'сумму (например, 123.45)', 'bank': 'название банка',
        'author': 'отправитель', 'procedure': 'назначение'
    }
    prompt_text = f"Хорошо, введите новое значение для поля *'{field_labels.get(field_to_edit, field_to_edit)}'*:"
    await query.edit_message_text(prompt_text, parse_mode='Markdown')
    return STATE_AWAITING_EDIT_VALUE

async def handle_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    field = context.user_data.get('field_to_edit')
    if not field:
        logger.warning("Попытка изменить значение без `field_to_edit` в user_data.")
        await _show_summary(update, context, "Произошла ошибка, давайте вернемся к проверке.")
        return STATE_CONFIRMATION

    new_value = update.message.text.strip()

    if field == 'amount':
        try:
            cleaned_value = re.sub(r'[^\d,.]', '', new_value).replace(',', '.')
            context.user_data[field] = float(cleaned_value)
        except (ValueError, TypeError):
            await update.message.reply_text(
                "Хм, это не похоже на сумму. Пожалуйста, введите число, например: `1500.50`.\nПопробуйте ещё раз.",
                parse_mode='Markdown'
            )
            return STATE_AWAITING_EDIT_VALUE
    elif field == 'date':
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', new_value):
            await update.message.reply_text(
                "Ой, неверный формат даты. Пожалуйста, введите её как `ДД.ММ.ГГГГ`, например: `08.10.2025`.\nПопробуйте снова.",
                parse_mode='Markdown'
            )
            return STATE_AWAITING_EDIT_VALUE
        context.user_data[field] = new_value
    else:
        context.user_data[field] = new_value

    context.user_data.pop('field_to_edit', None)
    await _show_summary(update, context, "Готово, поле обновлено! Давайте ещё раз всё проверим:")
    return STATE_CONFIRMATION

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['comment'] = update.message.text.strip()
    await _show_summary(update, context, "Комментарий добавлен! ✨ Теперь всё выглядит правильно?")
    return STATE_CONFIRMATION

def setup_handlers():
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            STATE_AWAITING_TYPE: [
                CallbackQueryHandler(handle_type, pattern='^(income|expense|transaction)$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_invalid_input)
            ],
            STATE_AWAITING_PET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pet),
                MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.TEXT, handle_invalid_input)
            ],
            STATE_AWAITING_PHOTO: [
                MessageHandler(filters.PHOTO, handle_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_invalid_input)
            ],
            STATE_CONFIRMATION: [
                CallbackQueryHandler(handle_confirmation, pattern='^(save|edit|add_comment|cancel)$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_invalid_input)
            ],
            STATE_EDITING_CHOICE: [
                CallbackQueryHandler(handle_editing_choice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_invalid_input)
            ],
            STATE_AWAITING_EDIT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_value),
                MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.TEXT, handle_invalid_input)
            ],
            STATE_AWAITING_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment),
                MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.TEXT, handle_invalid_input)
            ],
            STATE_DONE: [
                CallbackQueryHandler(start, pattern='^restart_flow$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_invalid_input)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CommandHandler('start', start),
        ]
    )

    help_handler = CommandHandler('help', help_command)

    return conv_handler, help_handler