# test_import.py
try:
    from app.bot.keyboards import get_transaction_type_keyboard
    print("✅ Успешный импорт!")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")