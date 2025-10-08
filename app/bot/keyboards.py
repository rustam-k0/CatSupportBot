# app/bot/keyboards.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_transaction_type_keyboard():
    """Клавиатура для выбора типа операции (Приход/Расход)."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Приход (донат)", callback_data="income"),
            InlineKeyboardButton("❌ Расход (покупка)", callback_data="expense"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_confirmation_keyboard():
    """Клавиатура для финального подтверждения данных."""
    keyboard = [
        [InlineKeyboardButton("💾 Сохранить", callback_data="save")],
        [InlineKeyboardButton("✏️ Исправить", callback_data="edit")],
        [InlineKeyboardButton("📝 Добавить комментарий", callback_data="add_comment")],
        [InlineKeyboardButton("✖️ Отмена", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_editing_keyboard(transaction_data: dict):
    """Динамическая клавиатура для выбора поля для редактирования."""
    keyboard = []
    editable_fields = {'pet_name': 'Питомец', 'date': 'Дата', 'amount': 'Сумма', 'author': 'Автор'}
    
    # ДОБАВЛЯЕМ КОНТЕКСТНО-ЗАВИСИМЫЕ ПОЛЯ
    if transaction_data.get('type') == 'income':
        editable_fields['bank'] = 'Банк'
    else: # expense
        editable_fields['procedure'] = 'Процедура'
    
    for field, label in editable_fields.items():
        value = transaction_data.get(field, 'не задано')
        keyboard.append([InlineKeyboardButton(f"{label}: {value}", callback_data=f"edit_{field}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад к подтверждению", callback_data="edit_back")])
    return InlineKeyboardMarkup(keyboard)