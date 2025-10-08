# app/services/vision_ocr.py

import logging
from google.cloud import vision
from google.api_core.exceptions import GoogleAPICallError, PermissionDenied

# ... (код инициализации клиента остается без изменений) ...
try:
    vision_client = vision.ImageAnnotatorClient()
    logging.info("Google Vision client initialized successfully.")
except Exception as e:
    vision_client = None
    logging.error(f"Could not initialize Google Vision client: {e}")

async def recognize_text(image_bytes: bytes) -> str | None:
    if not vision_client:
        logging.error("Vision client is not available.")
        return "КЛИЕНТ VISION НЕ ИНИЦИАЛИЗИРОВАН"

    try:
        image = vision.Image(content=image_bytes)
        response = vision_client.text_detection(image=image)

        if response.error.message:
            logging.error(f'Vision API error: {response.error.message}')
            # Возвращаем саму ошибку, чтобы увидеть её в боте
            return f"ОШИБКА VISION API: {response.error.message}"

        # Если текст пустой, вернем специальное сообщение
        if not response.full_text_annotation.text:
            return None

        return response.full_text_annotation.text

    except PermissionDenied as e:
        logging.error(f"Permission Denied: {e}")
        # Это самая частая ошибка при проблемах с ключом
        return f"ОТКАЗАНО В ДОСТУПЕ (Permission Denied): Проверьте ваш ключ API. {e.message}"
    
    except GoogleAPICallError as e:
        logging.error(f"An API error occurred: {e}")
        return f"ОШИБКА GOOGLE API: {e.message}"