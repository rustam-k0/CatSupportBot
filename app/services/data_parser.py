import re
from datetime import datetime
import locale
import logging

logger = logging.getLogger(__name__)

# --- Инициализация локали для парсинга дат на русском ---
try:
    locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'Russian_Russia.1251')
    except locale.Error:
        logger.warning("Не удалось установить русскую локаль")

# --- Улучшенные паттерны для поиска сумм ---
AMOUNT_PATTERNS = [
    # Приоритет 1: Прямые указания суммы
    re.compile(r'(?:сумма|итог|total|amount|transfer|пополнение|списано|оплата)[\s:]*([0-9]+[.,]?[0-9]*)[\s]*(?:руб|₽|р\.)?', re.IGNORECASE),
    # Приоритет 2: Форматы с валютой
    re.compile(r'([0-9]+[.,][0-9]{2})\s*(?:руб|₽|р\.)', re.IGNORECASE),
    # Приоритет 3: Любое число с плавающей точкой
    re.compile(r'(\d+[.,]\d{2})(?!\d)'),
]

DATE_PATTERNS = [
    re.compile(r'\b(\d{2}[./-]\d{2}[./-]\d{4})\b'),
    re.compile(r'\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})', re.IGNORECASE),
    re.compile(r'\b(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})', re.IGNORECASE),
]

AUTHOR_PATTERNS = [
    re.compile(r'(?:отправитель|sender|держатель|плательщик|from|имя)[\s:]*([А-ЯЁ][а-яё\s.-]+\b)', re.IGNORECASE),
    re.compile(r'\b([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)*)\b'),
]

def _normalize_amount(text: str) -> str:
    """Нормализует строку с суммой для преобразования в float."""
    return text.replace(' ', '').replace(',', '.')

def parse_amount(text: str) -> float | None:
    """Многоуровневый поиск суммы в тексте."""
    lines = text.split('\n')
    
    for pattern in AMOUNT_PATTERNS:
        for line in lines:
            match = pattern.search(line)
            if match:
                try:
                    amount_str = _normalize_amount(match.group(1))
                    # Убираем лишние точки (для форматов типа 1.000,50)
                    if amount_str.count('.') > 1:
                        parts = amount_str.split('.')
                        amount_str = '.'.join(parts[:-1]) + '.' + parts[-1]
                    return float(amount_str)
                except (ValueError, IndexError) as e:
                    logger.debug(f"Ошибка парсинга суммы '{match.group(1)}': {e}")
                    continue

    # Резервный поиск: наибольшее число в тексте
    numbers = []
    for line in lines:
        # Пропускаем строки с ID, номерами карт и т.д.
        if any(kw in line.lower() for kw in ['карта', 'счет', 'id', '№', 'number']):
            continue
            
        matches = re.findall(r'\b\d+[.,]?\d*\b', line)
        for match in matches:
            try:
                num = float(_normalize_amount(match))
                numbers.append(num)
            except ValueError:
                continue
    
    return max(numbers) if numbers else None

def parse_date(text: str) -> str | None:
    """Универсальный поиск даты в тексте."""
    for line in text.split('\n'):
        for pattern in DATE_PATTERNS:
            match = pattern.search(line)
            if match:
                try:
                    if len(match.groups()) == 1:
                        # Формат DD.MM.YYYY
                        date_str = match.group(1).replace('/', '.').replace('-', '.')
                        dt_object = datetime.strptime(date_str, "%d.%m.%Y")
                    else:
                        # Текстовый формат
                        day, month_str, year = match.groups()
                        month_dict = {
                            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
                            'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
                            'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12,
                            'january': 1, 'february': 2, 'march': 3, 'april': 4,
                            'may': 5, 'june': 6, 'july': 7, 'august': 8,
                            'september': 9, 'october': 10, 'november': 11, 'december': 12
                        }
                        month = month_dict.get(month_str.lower())
                        if month:
                            dt_object = datetime(int(year), month, int(day))
                        else:
                            continue
                    
                    return dt_object.strftime("%d.%m.%Y")
                except (ValueError, IndexError) as e:
                    logger.debug(f"Ошибка парсинга даты '{match.group(0)}': {e}")
                    continue
    return None

def parse_author(text: str) -> str | None:
    """Поиск автора/отправителя."""
    for pattern in AUTHOR_PATTERNS:
        match = pattern.search(text)
        if match:
            author = " ".join(match.group(1).split())
            # Фильтруем слишком короткие или нерелевантные совпадения
            if len(author) > 2 and author.lower() not in ['отправитель', 'плательщик']:
                return author
    return None

def parse_bank(text: str) -> str | None:
    """Ищет в тексте упоминания банков по ключевым словам."""
    BANK_KEYWORDS = {
        'сбер': 'Сбербанк', 'сбербанк': 'Сбербанк',
        'тинькофф': 'Т-Банк', 'tinkoff': 'Т-Банк',
        'т-банк': 'Т-Банк', 'тбанк': 'Т-Банк',
        'альфа': 'Альфа-Банк', 'альфабанк': 'Альфа-Банк', 'alfa': 'Альфа-Банк',
        'втб': 'ВТБ', 'втб24': 'ВТБ', 'vtb': 'ВТБ',
        'газпром': 'Газпромбанк', 'газпромбанк': 'Газпромбанк',
        'открытие': 'Банк Открытие', 'openbank': 'Банк Открытие',
    }
    
    lower_text = text.lower()
    for keyword, bank_name in BANK_KEYWORDS.items():
        if keyword in lower_text:
            return bank_name
    return None