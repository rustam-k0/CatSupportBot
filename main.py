# main.py

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from telegram.ext import Application

from config.settings import settings
from app.bot.handlers import setup_handlers

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Проверяем наличие ключевых переменных окружения
if not settings.telegram_token:
    logger.critical("TELEGRAM_TOKEN не установлен! Бот не может быть запущен.")
    raise ValueError("TELEGRAM_TOKEN обязателен для работы бота")

# Проверяем наличие файла с ключами доступа Google
if not os.path.exists("credentials.json"):
    logger.critical("Файл credentials.json не найден в корне проекта! Доступ к Google API невозможен.")

# --- Инициализация Telegram-бота ---
try:
    ptb_app_builder = Application.builder().token(settings.telegram_token)
    ptb_app = ptb_app_builder.build()
    
    # Регистрация обработчиков
    conv_handler, help_handler = setup_handlers()
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
        await ptb_app.start() 
        await ptb_app.updater.start_polling()
        logger.info("Бот успешно запущен")
        
        yield
        
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
    return {
        "status": "Bot is running via FastAPI", 
        "bot_running": ptb_app.updater.running if ptb_app.updater else False
    }

@app.get("/health", summary="Проверка здоровья сервиса")
def health_check():
    """Эндпоинт для систем мониторинга."""
    return {"status": "healthy", "bot_running": ptb_app.updater.running if ptb_app.updater else False}

# Если файл запускается напрямую (для локальной разработки)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)