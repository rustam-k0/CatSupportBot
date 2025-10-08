import gspread
import os
from gspread.exceptions import WorksheetNotFound, SpreadsheetNotFound, APIError
import logging

logger = logging.getLogger(__name__)

# --- Конфигурация ---
# Файл лежит в корне проекта
CREDENTIALS_FILE = "credentials.json"
SPREADSHEET_NAME = "HvostatyeSosediBot_DB"

# Заголовки для разных типов листов
INCOME_HEADERS = ["Дата", "Банк", "Сумма", "Комментарий", "Автор"]
EXPENSE_HEADERS = ["Питомец", "Дата", "Сумма", "Комментарий", "Автор"]

def get_spreadsheet_link(spreadsheet, worksheet):
    """Формирует прямую ссылку на конкретный лист в таблице."""
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit#gid={worksheet.id}"

def write_transaction(pet_name: str, transaction_data: dict) -> str | None:
    """
    Записывает данные о транзакции в Google Sheets с улучшенной обработкой ошибок.
    """
    # Проверяем наличие файла credentials
    if not os.path.exists(CREDENTIALS_FILE):
        logger.error(f"Файл {CREDENTIALS_FILE} не найден в корне проекта!")
        return None

    try:
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = gc.open(SPREADSHEET_NAME)
        logger.info(f"Успешно открыта таблица: {SPREADSHEET_NAME}")
    except SpreadsheetNotFound:
        logger.error(f"Таблица '{SPREADSHEET_NAME}' не найдена.")
        return None
    except Exception as e:
        logger.error(f"Ошибка доступа к Google Sheets: {e}")
        return None

    try:
        worksheet = spreadsheet.worksheet(pet_name)
        logger.info(f"Найден существующий лист: {pet_name}")
    except WorksheetNotFound:
        # Создаем новый лист если не найден
        logger.info(f"Лист '{pet_name}' не найден, создаю новый...")
        try:
            if transaction_data.get('type') == 'income':
                worksheet = spreadsheet.add_worksheet(title=pet_name, rows="100", cols="10")
                worksheet.append_row(INCOME_HEADERS)
                logger.info(f"Создан новый лист для приходов: {pet_name}")
            else: # expense
                worksheet = spreadsheet.add_worksheet(title=pet_name, rows="100", cols="10")
                worksheet.append_row(EXPENSE_HEADERS)
                logger.info(f"Создан новый лист для расходов: {pet_name}")
        except Exception as e:
            logger.error(f"Ошибка создания листа: {e}")
            return None

    # Формируем строку для записи
    try:
        if transaction_data.get('type') == 'income':
            row_to_add = [
                transaction_data.get('date', ''),
                transaction_data.get('bank', ''),
                transaction_data.get('amount', ''),
                transaction_data.get('comment', ''),
                transaction_data.get('author', '')
            ]
        else: # expense
            row_to_add = [
                transaction_data.get('pet_name', ''),
                transaction_data.get('date', ''),
                transaction_data.get('amount', ''),
                transaction_data.get('comment', ''),
                transaction_data.get('author', '')
            ]

        # Добавляем timestamp для отладки
        logger.info(f"Добавляем строку: {row_to_add}")
        
        worksheet.append_row(row_to_add)
        logger.info(f"Запись успешно добавлена для питомца '{pet_name}'")
        
        # Возвращаем ссылку на лист
        return get_spreadsheet_link(spreadsheet, worksheet)
        
    except APIError as e:
        logger.error(f"Ошибка API Google Sheets: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при добавлении строки: {e}")
        return None