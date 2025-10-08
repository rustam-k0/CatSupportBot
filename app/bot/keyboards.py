from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_transaction_type_keyboard():
    """Клавиатура для выбора типа операции."""
    keyboard = [
        [InlineKeyboardButton("✅ Приход (донат)", callback_data="type_income")],
        [InlineKeyboardButton("❌ Расход (покупка)", callback_data="type_expense")],
        [InlineKeyboardButton("Отменить", callback_data="action_cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_confirmation_keyboard():
    """Клавиатура с полным набором действий для подтверждения."""
    keyboard = [
        [InlineKeyboardButton("✅ Всё верно, сохранить", callback_data="confirm_save")],
        [InlineKeyboardButton("✏️ Исправить данные", callback_data="confirm_edit")],
        [
            InlineKeyboardButton("🔄 Начать заново", callback_data="action_restart"),
            InlineKeyboardButton("❌ Отменить", callback_data="action_cancel"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_editing_keyboard(transaction_data: dict):
    """Динамическая клавиатура для выбора поля для редактирования."""
    keyboard = []
    # Поля, которые можно редактировать
    editable_fields = {'pet_name': 'Питомец', 'date': 'Дата', 'amount': 'Сумма', 'author': 'Автор'}
    if transaction_data.get('type') == 'income':
        editable_fields['bank'] = 'Банк'
    
    for field, label in editable_fields.items():
        value = transaction_data.get(field, 'не задано')
        keyboard.append([InlineKeyboardButton(f"{label}: {value}", callback_data=f"edit_{field}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад к подтверждению", callback_data="edit_back")])
    return InlineKeyboardMarkup(keyboard)