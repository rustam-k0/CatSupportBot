# main.py

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from telegram.ext import Application

from config.settings import settings
# Импортируем setup_handlers вместо конкретных обработчиков
from app.bot.handlers import setup_handlers

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING) # Убираем лишние логи от HTTP-клиента
logger = logging.getLogger(__name__)

# Проверяем наличие ключевых переменных окружения
if not settings.telegram_token:
    logger.critical("TELEGRAM_TOKEN не установлен! Бот не может быть запущен.")
    raise ValueError("TELEGRAM_TOKEN обязателен для работы бота")

# Проверяем наличие файла с ключами доступа Google
if not os.path.exists("credentials.json"):
    logger.critical("Файл credentials.json не найден в корне проекта! Доступ к Google API невозможен.")
    # В реальном приложении здесь можно было бы завершить работу, но для FastAPI оставим возможность запуска
    # raise FileNotFoundError("credentials.json не найден")

# --- Инициализация Telegram-бота ---
try:
    ptb_app_builder = Application.builder().token(settings.telegram_token)
    # Можно добавить настройки персистентности, если нужно сохранять диалоги после перезапуска
    # ptb_app_builder.persistence(PicklePersistence(filepath="bot_persistence"))
    ptb_app = ptb_app_builder.build()
    
    # --- Регистрация обработчиков ---
    # Получаем обработчики из функции setup_handlers
    conv_handler, help_handler = setup_handlers()
    
    # Главный обработчик - это диалог. Остальные команды (как /help) добавляются отдельно.
    # Это предотвращает конфликты, когда /start или /cancel могут быть перехвачены до диалога.
    ptb_app.add_handler(conv_handler)
    ptb_app.add_handler(help_handler)
    
    logger.info("Бот и обработчики успешно инициализированы")
except Exception as e:
    logger.critical(f"Критическая ошибка инициализации бота: {e}", exc_info=True)
    raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управляет жизненным циклом: запускает и останавливает бота вместе с FastAPI."""
    logger.info("Запуск Telegram-бота в режиме polling...")
    try:
        await ptb_app.initialize()
        # Запускаем non-blocking, чтобы не мешать FastAPI
        await ptb_app.start() 
        await ptb_app.updater.start_polling()
        logger.info("Бот успешно запущен")
        
        yield # FastAPI приложение работает здесь
        
    finally:
        logger.info("Остановка Telegram-бота...")
        try:
            await ptb_app.updater.stop()
            await ptb_app.stop()
            await ptb_app.shutdown()
            logger.info("Бот успешно остановлен")
        except Exception as e:
            logger.error(f"Ошибка при остановке бота: {e}", exc_info=True)

# Создаем FastAPI приложение
app = FastAPI(
    title="HvostatyeSosediBot",
    description="Telegram бот для учета финансов зооволонтерских проектов",
    lifespan=lifespan
)

@app.get("/", summary="Статус бота")
def read_root():
    """Корневой эндпоинт для проверки, что веб-сервер запущен."""
    bot_info = ptb_app.bot.get_me() if ptb_app.bot else None
    return {
        "status": "Bot is running via FastAPI", 
        "bot_username": bot_info.username if bot_info else "Unknown"
    }

@app.get("/health", summary="Проверка здоровья сервиса")
def health_check():
    """Эндпоинт для систем мониторинга."""
    return {"status": "healthy", "bot_running": ptb_app.updater.running if ptb_app.updater else False}

# Если файл запускается напрямую (для локальной разработки)
if __name__ == "__main__":
    import uvicorn
    # `reload=True` удобно для разработки, uvicorn будет перезапускаться при изменении кода
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)