

import gspread

# Название файла с ключами, который вы скачали
CREDENTIALS_FILE = "credentials.json"
# Точное название вашей Google-таблицы
SPREADSHEET_NAME = "HvostatyeSosediBot_DB"

def add_test_record():
    """
    Добавляет тестовую строку в Google-таблицу.
    """
    try:
        # Авторизуемся с помощью файла credentials.json
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        
        # Открываем таблицу по названию
        spreadsheet = gc.open(SPREADSHEET_NAME)
        
        # Выбираем первый лист
        worksheet = spreadsheet.sheet1
        
        # Данные для тестовой записи
        test_data = ["15.01.2025", "500", "Тестовый донат от бота"]
        
        # Добавляем строку в конец таблицы
        worksheet.append_row(test_data)
        
        print(f"Запись '{test_data}' успешно добавлена в таблицу.")
        return True
    except Exception as e:
        print(f"Ошибка при работе с Google Sheets: {e}")
        return False