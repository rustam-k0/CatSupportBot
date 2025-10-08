import logging
import os
from google.cloud import vision
from google.api_core.exceptions import GoogleAPICallError, PermissionDenied, InvalidArgument

logger = logging.getLogger(__name__)

# Инициализация клиента с проверкой credentials
try:
    # Проверяем наличие файла credentials в корне проекта
    credentials_path = "credentials.json"
    if os.path.exists(credentials_path):
        vision_client = vision.ImageAnnotatorClient.from_service_account_file(credentials_path)
        logger.info(f"Google Vision client initialized with {credentials_path}")
    else:
        logger.error(f"Файл {credentials_path} не найден в корне проекта!")
        vision_client = None
        
except Exception as e:
    vision_client = None
    logger.error(f"Could not initialize Google Vision client: {e}")

async def recognize_text(image_bytes: bytes) -> str | None:
    """Распознает текст с изображения с улучшенной обработкой ошибок."""
    if not vision_client:
        error_msg = "Клиент Vision не инициализирован. Проверьте credentials.json"
        logger.error(error_msg)
        return error_msg

    try:
        image = vision.Image(content=image_bytes)
        response = vision_client.text_detection(image=image)

        if response.error.message:
            error_msg = f'Ошибка Vision API: {response.error.message}'
            logger.error(error_msg)
            return error_msg

        texts = response.text_annotations
        if not texts:
            return "Текст не обнаружен на изображении"

        # Возвращаем весь распознанный текст
        full_text = texts[0].description
        logger.info(f"Успешно распознано {len(full_text)} символов")
        return full_text

    except PermissionDenied as e:
        error_msg = f"Доступ запрещен: {e}. Проверьте права сервисного аккаунта."
        logger.error(error_msg)
        return error_msg
    except InvalidArgument as e:
        error_msg = f"Неверный аргумент: {e}. Проверьте формат изображения."
        logger.error(error_msg)
        return error_msg
    except GoogleAPICallError as e:
        error_msg = f"Ошибка Google API: {e}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Неожиданная ошибка: {e}"
        logger.error(error_msg)
        return error_msg