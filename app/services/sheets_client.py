import gspread
import os
from gspread.exceptions import APIError, WorksheetNotFound
import logging

logger = logging.getLogger(__name__)

CREDENTIALS_FILE = "credentials.json"
SPREADSHEET_NAME = "HvostatyeSosediBot_DB"
TEMPLATE_SHEET_NAME = "Шаблон"

INCOME_COLS = {
    "start": "A", "end": "E", "check_col_index": 1,
}
EXPENSE_COLS = {
    "start": "G", "end": "K", "check_col_index": 7,
}

def get_spreadsheet_link(spreadsheet: gspread.Spreadsheet, worksheet: gspread.Worksheet) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit#gid={worksheet.id}"

def _create_fallback_worksheet(spreadsheet: gspread.Spreadsheet, sheet_name: str) -> gspread.Worksheet | None:
    logger.warning(f"Шаблон '{TEMPLATE_SHEET_NAME}' не найден! Создается базовый лист для '{sheet_name}'.")
    try:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows="300", cols="20")
        
        worksheet.update('F1', sheet_name)
        worksheet.update('A2', 'Приход')
        worksheet.update('G2', 'Расход')
        
        income_headers = ["Дата", "Сумма", "Банк", "Автор", "Комментарий"]
        expense_headers = ["Дата", "Сумма", "Процедура", "Автор", "Комментарий"]
        worksheet.update('A3', [income_headers])
        worksheet.update('G3', [expense_headers])
        
        return worksheet
    except APIError as e:
        logger.error(f"Не удалось создать даже базовый лист: {e}")
        return None

def _find_or_create_worksheet(spreadsheet: gspread.Spreadsheet, pet_name: str) -> gspread.Worksheet | None:
    try:
        return spreadsheet.worksheet(pet_name)
    except WorksheetNotFound:
        logger.info(f"Лист для '{pet_name}' не найден. Ищем шаблон '{TEMPLATE_SHEET_NAME}' для копирования.")

    try:
        template_worksheet = spreadsheet.worksheet(TEMPLATE_SHEET_NAME)
        new_worksheet = template_worksheet.duplicate(new_sheet_name=pet_name)
        new_worksheet.update_cell(1, 6, pet_name)
        
        logger.info(f"✅ Шаблон '{TEMPLATE_SHEET_NAME}' успешно скопирован в новый лист '{pet_name}'.")
        return new_worksheet
    except WorksheetNotFound:
        return _create_fallback_worksheet(spreadsheet, pet_name)
    except APIError as e:
        logger.error(f"Ошибка API при копировании шаблона: {e}")
        return None

def write_transaction(transaction_data: dict) -> str | None:
    if not os.path.exists(CREDENTIALS_FILE):
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Файл {CREDENTIALS_FILE} не найден!")
        return None

    try:
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = gc.open(SPREADSHEET_NAME)
    except Exception as e:
        logger.error(f"Не удалось получить доступ к Google Sheets: {e}", exc_info=True)
        return None

    pet_name = transaction_data.get('pet_name', '').strip().capitalize()
    if not pet_name:
        logger.error("В данных транзакции отсутствует 'pet_name'. Операция прервана.")
        return None

    worksheet = _find_or_create_worksheet(spreadsheet, pet_name)
    if not worksheet:
        return None

    trans_type = transaction_data.get('type')
    
    if trans_type in ['income', 'transaction']:
        target_cols = INCOME_COLS
        row_data = [
            transaction_data.get('date', ''),
            transaction_data.get('amount', ''),
            transaction_data.get('bank', ''),
            transaction_data.get('author', ''),
            transaction_data.get('comment', '')
        ]
    elif trans_type == 'expense':
        target_cols = EXPENSE_COLS
        row_data = [
            transaction_data.get('date', ''),
            transaction_data.get('amount', ''),
            transaction_data.get('procedure', ''),
            transaction_data.get('author', ''),
            transaction_data.get('comment', '')
        ]
    else:
        logger.error(f"Неизвестный тип транзакции: '{trans_type}'")
        return None

    try:
        col_values = worksheet.col_values(target_cols["check_col_index"])
        next_row = len(col_values) + 1
        if next_row < 4: next_row = 4
        
        write_range = f'{target_cols["start"]}{next_row}:{target_cols["end"]}{next_row}'
        worksheet.update(write_range, [row_data], value_input_option='USER_ENTERED')
        
        sheet_link = get_spreadsheet_link(spreadsheet, worksheet)
        
        logger.info(f"✅ Запись добавлена на лист '{worksheet.title}', диапазон {write_range}")
        logger.info(f"📎 Ссылка на лист: {sheet_link}")
        return sheet_link
    except Exception as e:
        logger.error(f"⚠️ Ошибка при записи данных на лист '{worksheet.title}': {e}", exc_info=True)
        return None