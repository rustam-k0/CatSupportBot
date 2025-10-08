# app/services/data_parser.py

import re
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def _clean_text(text: str) -> str:
    """Вспомогательная функция для очистки и нормализации текста."""
    # Заменяем распространенные опечатки OCR
    text = text.replace('Р', '₽').replace('Р.', '₽').replace('руб.', '₽')
    # Добавляем пробелы вокруг, чтобы регулярные выражения с \b работали надежнее
    return f' {text} '

def parse_amount(text: str) -> float | None:
    """
    Ищет сумму в тексте, используя каскадный пошаговый поиск.
    1. Ищет точные ключевые слова.
    2. Ищет сумму на отдельной строке с валютой.
    3. Ищет числа в формате "1 234,56".
    4. Ищет любое число рядом со знаком валюты.
    """
    clean_text = _clean_text(text)
    
    PATTERNS = [
        # 1. ТОЧНОЕ СООТВЕТСТВИЕ: Ключевое слово + число
        {'desc': 'Ключевое слово (Сумма, Итог)', 'regex': r'(?:Сумма|Итог|Всего|Total|Amount)[\s:]+([\d\s,.]+)', 'flags': re.IGNORECASE},
        
        # 2. ПОИСК ПО ФОРМАТУ: Число с валютой на отдельной строке (самый частый кейс)
        {'desc': 'Число с валютой на отдельной строке', 'regex': r'^\s*([\d\s,.]+[\d])\s*₽\s*$', 'flags': re.IGNORECASE | re.MULTILINE},
        
        # 3. ПОИСК ПО ПОХОЖЕМУ ФОРМАТУ: Числа с разделителями-запятыми/пробелами
        {'desc': 'Число с копейками (1,234.56)', 'regex': r'\b(\d{1,3}(?:\s\d{3})*[,.]\d{2})\b', 'flags': 0},
        
        # 4. ОБЩИЙ ПОИСК: Любое число рядом со знаком валюты
        {'desc': 'Любое число рядом с ₽', 'regex': r'([\d\s,.]+[\d])\s*₽', 'flags': re.IGNORECASE},
    ]

    for p in PATTERNS:
        match = re.search(p['regex'], clean_text, p['flags'])
        if match:
            try:
                amount_str = match.group(1).replace(' ', '').replace(',', '.')
                logger.info(f"✅ Сумма найдена (шаблон: \"{p['desc']}\"): {amount_str}")
                return float(amount_str)
            except (ValueError, IndexError):
                continue
    
    logger.warning("⚠️ Не удалось найти сумму ни одним из шаблонов.")
    return None

def parse_date(text: str) -> str | None:
    """Ищет дату в различных форматах (ДД.ММ.ГГГГ, ДД/ММ/ГГГГ) и валидирует ее."""
    # Паттерн ищет дату с разделителями '.', '/' или '-'
    match = re.search(r'\b(\d{2}[./-]\d{2}[./-]\d{2,4})\b', text)
    if match:
        try:
            date_str = match.group(1).replace('/', '.').replace('-', '.')
            # Попытка распознать полный год
            if len(date_str.split('.')[-1]) == 4:
                dt_obj = datetime.strptime(date_str, "%d.%m.%Y")
            else: # Распознавание короткого года
                dt_obj = datetime.strptime(date_str, "%d.%m.%y")
            
            full_date_str = dt_obj.strftime("%d.%m.%Y")
            logger.info(f"✅ Дата найдена и нормализована: {full_date_str}")
            return full_date_str
        except ValueError:
            logger.warning(f"⚠️ Найдена строка, похожая на дату, но невалидная: {match.group(1)}")
    return None

def parse_author(text: str) -> str | None:
    """
    Ищет автора/отправителя, используя каскадный пошаговый поиск.
    1. Точное соответствие с ключевыми словами.
    2. Синонимы и сокращения.
    3. Популярные форматы имен без ключевых слов.
    4. Названия компаний в кавычках.
    """
    PATTERNS = [
        # 1. ТОЧНОЕ СООТВЕТСТВИЕ: Ключевое слово + Имя
        {'desc': 'Ключевое слово (Отправитель)', 'regex': r'(?:Отправитель|Sender|Плательщик)[\s:]+([А-ЯЁа-яё\s.]+)', 'flags': re.IGNORECASE},
        
        # 2. СИНОНИМЫ:
        {'desc': 'Синоним (От кого, Клиент)', 'regex': r'(?:От кого|Клиент|From)[\s:]+([А-ЯЁа-яё\s.]+)', 'flags': re.IGNORECASE},

        # 3. ПОИСК ПО ФОРМАТУ: Популярные форматы имен без ключевых слов
        {'desc': 'Формат "ФАМИЛИЯ И. О."', 'regex': r'\b([А-ЯЁ]{3,}\s[А-ЯЁ]\.\s?[А-ЯЁ]\.)\b', 'flags': 0},
        {'desc': 'Формат "Имя Ф."', 'regex': r'\b([А-ЯЁ][а-яё]+\s[А-ЯЁ]\.)\b', 'flags': 0},
        
        # 4. ОБЩИЙ ПОИСК: Название в кавычках
        {'desc': 'Название в кавычках', 'regex': r'[«"]([^»"]+)[»"]', 'flags': 0},
    ]

    for p in PATTERNS:
        match = re.search(p['regex'], text, p['flags'])
        if match:
            # Убираем лишние пробелы и точки из найденной строки
            author = re.sub(r'[\s.]+$', '', match.group(1).strip())
            logger.info(f"✅ Автор найден (шаблон: \"{p['desc']}\"): {author}")
            return author
            
    logger.warning("⚠️ Не удалось найти автора ни одним из шаблонов.")
    return None

def parse_bank(text: str) -> str | None:
    """Ищет название банка по ключевым словам. Более устойчив к форматированию."""
    BANK_KEYWORDS = {
        'т-банк': 'Т-Банк', 'тбанк': 'Т-Банк', 'тинькофф': 'Т-Банк', 'tinkoff': 'Т-Банк',
        'сбербанк': 'Сбербанк', 'сбер': 'Сбер',
        'альфа-банк': 'Альфа-Банк', 'альфабанк': 'Альфа-Банк',
        'втб': 'ВТБ',
    }
    
    clean_text = ' ' + text.lower().replace('«', ' ').replace('»', ' ') + ' '
    
    for keyword, bank_name in BANK_KEYWORDS.items():
        if f' {keyword} ' in clean_text:
            logger.info(f"✅ Банк найден по ключевому слову '{keyword}': {bank_name}")
            return bank_name

    if 'яндекс' in clean_text and ('сбп' in clean_text or 'система быстрых платежей' in clean_text):
        logger.info("✅ Обнаружен перевод через Яндекс СБП")
        return 'Яндекс СБП'
        
    return None