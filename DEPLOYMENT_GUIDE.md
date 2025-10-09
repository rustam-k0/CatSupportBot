```markdown


📁 Назначение файлов

```
HvostatyeSosediBot/
├── main.py                 # 🎯 Точка входа FastAPI + Telegram бот
├── requirements.txt        # 📦 Зависимости Python
├── credentials.json        # 🔐 Ключи Google API (не в гите!)
├── .env                   # ⚙️  Переменные окружения (не в гите!)
├── config/
│   └── settings.py        # ⚙️  Настройки приложения
├── app/
│   ├── bot/
│   │   ├── handlers.py    # 🤖 Логика диалогов бота
│   │   └── keyboards.py   # ⌨️  Клавиатуры Telegram
│   ├── services/
│   │   ├── vision_ocr.py  # 👁️  Распознавание текста (Google Vision)
│   │   ├── data_parser.py # 🔍 Парсинг данных из текста
│   │   └── sheets_client.py # 📊 Запись в Google Sheets
│   └── models/
│       └── schemas.py     # 📝 Модели данных (Pydantic)
```





🚀 Полное руководство по развертыванию
1. Создание Telegram бота

1. Напишите [@BotFather](https://t.me/BotFather)

2. Команда: `/newbot`

3. Придумайте имя (например: `HvostatyeSosediBot`)

4. Получите токен: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`

5. Сохраните токен! Он понадобится позже

2. Настройка Google Cloud Project

2. 1 Создание проекта

1. Откройте [Google Cloud Console](https://console.cloud.google.com)

2. Нажмите "Create Project"

3. Название: `HvostatyeSosediBot`

4. Project ID: оставьте автоматический

2. 2 Включение API

1. В меню слева: "APIs & Services" → "Library"

2. Найдите и включите:
 * Google Sheets API
 * Google Cloud Vision API

2. 3 Создание Service Account

1. "APIs & Services" → "Credentials"

2. "Create Credentials" → "Service Account"

3. Имя: `hvostatye-bot-service`

4. Роль: `Editor` (или более ограниченные права)

5. Нажмите "Create Key" → "JSON"

6. Скачайте файл `credentials.json`

3. Настройка Google Таблицы

3. 1 Создание таблицы

1. Откройте [Google Sheets](https://sheets.google.com)

2. "Blank" → создайте новую таблицу

3. Название: `HvostatyeSosediBot_DB`

4. Скопируйте URL из адресной строки

3. 2 Настройка шаблона

1. Переименуйте первый лист в `Шаблон`

2. Настройте структуру:

Левый блок (Приход):
```
A1: Дата    B1: Сумма    C1: Банк    D1: Автор    E1: Комментарий
```

Правый блок (Расход):
```
G1: Дата    H1: Сумма    I1: Процедура    J1: Автор    K1: Комментарий
```

3. 3 Предоставление доступа

1. В таблице: "Share" → "Add people and groups"

2. Вставьте email из `credentials.json` (например: `hvostatye-bot-service@your-project.iam.gserviceaccount.com`)

3. Права: `Editor`

4. Развертывание на Render

4. 1 Подготовка репозитория
```bash
Убедитесь, что эти файлы НЕ в гите:
.gitignore
credentials.json
.env

.gitignore должен содержать:
credentials.json
.env
pycache/
* .pyc
```

4. 2 Создание сервиса на Render

1. Зайдите на [render.com](https://render.com)

2. "New" → "Web Service"

3. Подключите ваш GitHub репозиторий

4. Настройки:
 * Name: `hvostatye-sosedi-bot`
 * Environment: `Python 3`
 * Region: `Frankfurt` (или ближайший к вам)
 * Branch: `main` (или ваша ветка)
 * Build Command: `pip install -r requirements.txt`
 * Start Command: `uvicorn main:app --host=0.0.0.0 --port=$PORT`

4. 3 Настройка переменных окружения
В Render: Settings → Environment Variables:
```
TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
GOOGLESHEETSLINK=https://docs.google.com/spreadsheets/d/your-table-id/edit
```

4. 4 Загрузка credentials.json

1. В Render: Settings → Environment → Secret Files

2. "Add Secret File"

3. Name: `credentials.json`

4. Content: вставьте содержимое вашего файла

4. 5 Запуск

1. Нажмите "Create Web Service"

2. Ждите завершения деплоя (5-10 минут)

3. Проверьте логи на вкладке "Logs"

✅ Проверка работоспособности

1. Найдите бота в Telegram по имени

2. Отправьте `/start`

3. Протестируйте с простым чеком

4. Проверьте запись в Google таблице

🆘 Решение проблем

Бот не отвечает:
* Проверьте TELEGRAM_TOKEN в переменных
* Убедитесь, что бот не заблокирован

Ошибки Google API:
* Проверьте, что `credentials.json` загружен
* Убедитесь, что сервисный аккаунт имеет доступ к таблице

Таблица не создает листы:
* Проверьте название таблицы: `HvostatyeSosediBot_DB`
* Убедитесь, что есть лист `Шаблон`

---
🎉 Готово! Бот полностью настроен и готов к работе.
```
