from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_transaction_type_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📈 Добавить доход", callback_data="income"),
            InlineKeyboardButton("🛍️ Добавить расход", callback_data="expense"),
        ],
        [InlineKeyboardButton("💸 Транзакции", callback_data="transaction")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("✅ Всё верно, сохранить", callback_data="save")],
        [InlineKeyboardButton("✍️ Изменить данные", callback_data="edit")],
        [InlineKeyboardButton("💬 Добавить комментарий", callback_data="add_comment")],
        [InlineKeyboardButton("🚫 Отменить операцию", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_editing_keyboard(transaction_data: dict) -> InlineKeyboardMarkup:
    keyboard = []
    transaction_type = transaction_data.get('type')

    if transaction_type == 'transaction':
        editable_fields = {'pet_name': 'Подопечный', 'bank': 'Банк'}
    else:
        editable_fields = {'pet_name': 'Подопечный', 'date': 'Дата', 'amount': 'Сумма'}
        if transaction_type == 'income':
            editable_fields.update({'bank': 'Банк', 'author': 'Отправитель'})
        else:
            editable_fields.update({'procedure': 'Назначение', 'author': 'Продавец'})

    for field, label in editable_fields.items():
        value = transaction_data.get(field, 'не задано')
        keyboard.append([InlineKeyboardButton(f"{label}: {value}", callback_data=f"edit_{field}")])
    
    keyboard.append([InlineKeyboardButton("↩️ Вернуться к проверке", callback_data="edit_back")])
    return InlineKeyboardMarkup(keyboard)

def get_restart_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton("🔄 Начать новую запись", callback_data="restart_flow")]]
    return InlineKeyboardMarkup(keyboard)