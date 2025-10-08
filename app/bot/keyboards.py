from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_transaction_type_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для выбора типа операции."""
    keyboard = [
        [
            InlineKeyboardButton("📈 Добавить доход", callback_data="income"),
            InlineKeyboardButton("🛍️ Добавить расход", callback_data="expense"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для финального подтверждения операции."""
    keyboard = [
        [InlineKeyboardButton("✅ Всё верно, сохранить", callback_data="save")],
        [InlineKeyboardButton("✍️ Изменить данные", callback_data="edit")],
        [InlineKeyboardButton("💬 Добавить комментарий", callback_data="add_comment")],
        [InlineKeyboardButton("🚫 Отменить операцию", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_editing_keyboard(transaction_data: dict) -> InlineKeyboardMarkup:
    """
    Создаёт динамическую клавиатуру для выбора поля, которое нужно исправить.
    Кнопки меняются в зависимости от типа операции.
    """
    keyboard = []
    
    # Общие поля для всех операций
    editable_fields = {
        'pet_name': 'Подопечный', 
        'date': 'Дата', 
        'amount': 'Сумма'
    }
    
    # Поля, зависящие от типа операции
    transaction_type = transaction_data.get('type')
    if transaction_type == 'income':
        editable_fields['bank'] = 'Банк'
        editable_fields['author'] = 'Отправитель'
    else: # expense
        editable_fields['procedure'] = 'Назначение'
        editable_fields['author'] = 'Продавец'
    
    # Формируем кнопки с текущими значениями
    for field, label in editable_fields.items():
        value = transaction_data.get(field, 'не задано')
        keyboard.append([InlineKeyboardButton(f"{label}: {value}", callback_data=f"edit_{field}")])
    
    keyboard.append([InlineKeyboardButton("↩️ Вернуться к проверке", callback_data="edit_back")])
    
    return InlineKeyboardMarkup(keyboard)

def get_restart_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру с кнопкой для начала новой операции."""
    keyboard = [
        [InlineKeyboardButton("🔄 Начать новую запись", callback_data="restart_flow")]
    ]
    return InlineKeyboardMarkup(keyboard)
