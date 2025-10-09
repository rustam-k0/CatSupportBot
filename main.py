# main.py

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from telegram.ext import Application
from telegram import Update

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
    # На Render используем вебхуки вместо polling
    webhook_url = os.getenv("RENDER_EXTERNAL_URL", "") + "/webhook"
    
    if webhook_url and not webhook_url.startswith("http"):
        webhook_url = f"https://{webhook_url}"
    
    if webhook_url and "render.com" in webhook_url:
        logger.info(f"Настройка вебхука для Render: {webhook_url}")
        await ptb_app.initialize()
        await ptb_app.bot.set_webhook(webhook_url)
        await ptb_app.start()
        logger.info("Бот успешно запущен в режиме вебхука")
    else:
        # Локальная разработка с polling
        logger.info("Запуск Telegram-бота в режиме polling (локальная разработка)...")
        await ptb_app.initialize()
        await ptb_app.start() 
        if ptb_app.updater:
            await ptb_app.updater.start_polling()
        logger.info("Бот успешно запущен в режиме polling")
    
    yield
    
    logger.info("Остановка Telegram-бота...")
    try:
        if ptb_app.updater:
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

@app.post("/webhook")
async def webhook(request: Request):
    """Эндпоинт для получения обновлений от Telegram через вебхук."""
    try:
        data = await request.json()
        update = Update.de_json(data, ptb_app.bot)
        await ptb_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/", summary="Статус бота")
async def read_root():
    """Корневой эндпоинт для проверки, что веб-сервер запущен."""
    try:
        webhook_info = await ptb_app.bot.get_webhook_info()
        return {
            "status": "Bot is running via FastAPI",
            "webhook_url": webhook_info.url,
            "webhook_set": bool(webhook_info and webhook_info.url),
            "pending_updates": webhook_info.pending_update_count if webhook_info else 0
        }
    except Exception as e:
        logger.error(f"Ошибка получения информации о вебхуке: {e}")
        return {"status": "Bot is running", "error": str(e)}

@app.get("/health", summary="Проверка здоровья сервиса")
def health_check():
    """Эндпоинт для систем мониторинга."""
    return {"status": "healthy"}

@app.get("/set_webhook", summary="Установить вебхук вручную")
async def set_webhook_manual():
    """Эндпоинт для ручной установки вебхука (для отладки)."""
    try:
        webhook_url = os.getenv("RENDER_EXTERNAL_URL", "") + "/webhook"
        if webhook_url and not webhook_url.startswith("http"):
            webhook_url = f"https://{webhook_url}"
        
        result = await ptb_app.bot.set_webhook(webhook_url)
        return {
            "status": "webhook_set", 
            "url": webhook_url,
            "success": result
        }
    except Exception as e:
        logger.error(f"Ошибка установки вебхука: {e}")
        return {"status": "error", "message": str(e)}

# Если файл запускается напрямую (для локальной разработки)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)