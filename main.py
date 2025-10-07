import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from telegram.ext import Application

from config.settings import settings
from app.bot.handlers import start_handler, help_handler, photo_handler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# Создаем экземпляр PTB Application
ptb_app = Application.builder().token(settings.telegram_token).build()
ptb_app.add_handlers([start_handler, help_handler, photo_handler])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Код здесь выполняется ПЕРЕД запуском приложения
    logger.info("Starting bot...")
    await ptb_app.initialize()  # Инициализируем приложение бота
    await ptb_app.updater.start_polling()  # Запускаем поллинг
    await ptb_app.start()  # Запускаем само приложение (обработчики и т.д.)
    
    yield # В этот момент приложение работает
    
    # Код здесь выполняется ПОСЛЕ остановки приложения
    logger.info("Stopping bot...")
    await ptb_app.stop() # Останавливаем приложение
    await ptb_app.updater.stop()  # Останавливаем поллинг
    await ptb_app.shutdown()  # Корректно завершаем работу


# FastAPI приложение с настроенным жизненным циклом
app = FastAPI(lifespan=lifespan)


@app.get("/")
def read_root():
    return {"status": "Bot is running"}