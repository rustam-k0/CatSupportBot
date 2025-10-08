import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from telegram.ext import Application

from config.settings import settings
from app.bot.handlers import start_handler, help_handler, conv_handler, cancel_handler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Проверяем обязательные переменные
if not settings.telegram_token:
    logger.error("TELEGRAM_TOKEN не установлен!")
    raise ValueError("TELEGRAM_TOKEN обязателен для работы бота")

# Проверяем наличие credentials.json
if not os.path.exists("credentials.json"):
    logger.error("Файл credentials.json не найден в корне проекта!")

# Создаем экземпляр приложения python-telegram-bot
try:
    ptb_app = Application.builder().token(settings.telegram_token).build()
    logger.info("Бот успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка инициализации бота: {e}")
    raise

# Добавляем обработчики
try:
    ptb_app.add_handlers([
        start_handler,
        help_handler,
        cancel_handler,
        conv_handler
    ])
    logger.info("Обработчики успешно добавлены")
except Exception as e:
    logger.error(f"Ошибка добавления обработчиков: {e}")
    raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управляет жизненным циклом приложения."""
    logger.info("Запуск бота...")
    
    try:
        await ptb_app.initialize()
        await ptb_app.updater.start_polling()
        await ptb_app.start()
        logger.info("Бот успешно запущен")
        
        yield
        
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise
        
    finally:
        logger.info("Остановка бота...")
        try:
            await ptb_app.updater.stop()
            await ptb_app.stop()
            await ptb_app.shutdown()
            logger.info("Бот успешно остановлен")
        except Exception as e:
            logger.error(f"Ошибка при остановке бота: {e}")

# Создаем FastAPI приложение
app = FastAPI(
    title="HvostatyeSosediBot",
    description="Telegram бот для учета финансов зооволонтерских проектов",
    lifespan=lifespan
)

@app.get("/")
def read_root():
    """Корневой эндпоинт для проверки работоспособности."""
    return {
        "status": "Bot is running", 
        "bot_username": ptb_app.bot.username if ptb_app.bot else "Unknown"
    }

@app.get("/health")
def health_check():
    """Эндпоинт для проверки здоровья сервиса."""
    return {"status": "healthy", "bot_running": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)