# app/services/data_parser.py

import re
from datetime import datetime
import logging

# ============================================================================
# Настройка логгера для отслеживания процесса парсинга.
# ============================================================================
logger = logging.getLogger(__name__)

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def _clean_amount_string(s: str) -> float | None:
    """Очищает строку с суммой от лишних символов и преобразует в float."""
    if not isinstance(s, str):
        return None
    try:
        cleaned = re.sub(r'[^\d,.]', '', s)
        cleaned = cleaned.replace(',', '.')
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _normalize_text_for_search(text: str) -> str:
    """Нормализует текст для более надежного поиска."""
    if not isinstance(text, str):
        return ''
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

def _clean_author_string(author: str) -> str:
    """Дополнительно очищает найденную строку автора от мусора."""
    author = author.strip('.,;:"«» \n\t')
    author = re.sub(r'^(ООО|ИП|АО|ПАО|ЗАО|ОАО)\s+', '', author, flags=re.IGNORECASE).strip()
    author = author.strip('"«»')
    return author

# ============================================================================
# ОПРЕДЕЛЕНИЕ ШАБЛОНОВ ПОИСКА (ЦЕНТРАЛЬНОЕ МЕСТО ДЛЯ ИЗМЕНЕНИЙ)
# ============================================================================

def _get_date_patterns() -> list:
    """Возвращает шаблоны для поиска ДАТЫ."""
    return [
        {
            'tier': 1,
            'desc': 'Дата в числовом формате (ДД.ММ.ГГГГ)',
            'regex': r'\b(\d{2}[./-]\d{2}[./-]\d{2,4})\b',
            'type': 'numeric',
            'flags': 0
        },
        # НОВОЕ ПРАВИЛО: Добавлено для распознавания формата "8 октября 2025"
        {
            'tier': 2,
            'desc': 'Дата в текстовом формате (8 октября 2025)',
            'regex': r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})',
            'type': 'textual',
            'flags': re.IGNORECASE
        },
    ]

def _get_amount_patterns() -> list:
    """Возвращает иерархический список шаблонов для поиска СУММЫ."""
    AMOUNT_REGEX = r'([\d\s,.]+[\d])'
    CURRENCY_REGEX = r'(?:Р|₽|руб\.?|RUB)?'
    return [
        {'tier': 1, 'desc': 'Ключевое слово "Сумма/Итого/Всего" и число на одной строке', 'regex': fr'(?:Сумма|Итого|Всего|Сумма\sв\sвалюте\sоперации)\s*[:\s.]*\s*{AMOUNT_REGEX}\s*{CURRENCY_REGEX}', 'flags': re.IGNORECASE},
        {'tier': 2, 'desc': 'Ключевое слово на отдельной строке ВЫШЕ числа', 'regex': fr'(?:Сумма|Итого|Всего|Операция)\s*\n+\s*{AMOUNT_REGEX}\s*{CURRENCY_REGEX}', 'flags': re.IGNORECASE},
        {'tier': 2, 'desc': 'Синонимы: "К оплате", "Начислено", "Пополнение"', 'regex': fr'(?:К\sоплате|Начислено|Списано|Зачислено|Получено|Пополнение)\s*[:\s.]*\s*{AMOUNT_REGEX}', 'flags': re.IGNORECASE},
        {'tier': 3, 'desc': 'Сокращения: "Ст-ть", "Стоим-ть", "Цена"', 'regex': fr'(?:Ст-ть|Стоимость|Стоим-ть|Цена)\s*[:\s]*\s*{AMOUNT_REGEX}', 'flags': re.IGNORECASE},
        {'tier': 4, 'desc': 'Английские термины: "Amount", "Total", "Price"', 'regex': fr'(?:Amount|Total|Sum|Price)\s*[:\s]*\s*{AMOUNT_REGEX}', 'flags': re.IGNORECASE},
        {'tier': 5, 'desc': 'Число (3+ цифры) с явным символом валюты', 'regex': fr'([\d\s,.]' + r'{3,}' + fr')\s*(?:Р|₽|руб\.?|RUB)', 'flags': re.IGNORECASE},
        {'tier': 5, 'desc': 'Число с копейками (формат: 1234.56)', 'regex': r'\b(\d{1,3}(?:\s?\d{3})*[,.]\d{2})\b', 'flags': 0},
        {'tier': 5, 'desc': 'Большое число (>999) с пробелами-разделителями', 'regex': r'\b(\d{1,3}(?:\s\d{3})+[,.]?\d*)\b', 'flags': 0},
    ]

def _get_bank_patterns() -> list:
    """Возвращает шаблоны для поиска БАНКА."""
    BANK_KEYWORDS = {
        'Т-Банк': ['т-банк', 'тбанк', 'тинькофф', 'tinkoff'],
        'Сбербанк': ['сбербанк', 'сбер', 'sber', 'sberbank'],
        'Альфа-Банк': ['альфа-банк', 'альфа', 'alfa', 'alfabank'],
        'ВТБ': ['втб', 'vtb'],
        'Яндекс': ['яндекс', 'yandex'],
    }
    patterns = []
    for bank_name, keywords in BANK_KEYWORDS.items():
        regex = r'\b(' + '|'.join(keywords) + r')\b'
        patterns.append({'tier': 1, 'desc': f'Поиск по ключевым словам для "{bank_name}"', 'regex': regex, 'bank_name': bank_name, 'flags': re.IGNORECASE})
    return patterns

def _get_author_patterns(transaction_type: str) -> list:
    """Возвращает шаблоны для поиска АВТОРА в зависимости от типа транзакции."""
    AUTHOR_NAME_REGEX = r'([А-ЯЁа-яёA-Za-z\s."«»-]+?)'
    if transaction_type == 'income':
        return [
            {'tier': 1, 'desc': 'Ключ "Отправитель", "Банк отправителя", "Плательщик"', 'regex': fr'(?:Отправитель|Банк\sотправителя|Плательщик)\s*[:\s]*\n?\s*{AUTHOR_NAME_REGEX}(?=\n|$)', 'flags': re.IGNORECASE},
            {'tier': 2, 'desc': 'Синонимы: "От кого", "Источник"', 'regex': fr'(?:От\sкого|Источник)\s*[:\s]*\n?\s*{AUTHOR_NAME_REGEX}(?=\n|$)', 'flags': re.IGNORECASE},
            # НОВОЕ ПРАВИЛО: Добавлено для чеков Сбербанка
            {
                'tier': 2,
                'desc': 'Имя после слова "Описание"',
                'regex': r'Описание\n\s*([А-ЯЁа-яё\s]+\s[А-ЯЁ]\.)',
                'flags': re.IGNORECASE
            },
            {'tier': 4, 'desc': 'Английские термины: "From", "Sender"', 'regex': fr'(?:From|Sender)\s*[:\s]*\n?\s*{AUTHOR_NAME_REGEX}(?=\n|$)', 'flags': re.IGNORECASE},
            # УЛУЧШЕННОЕ ПРАВИЛО: Теперь распознает "Имя О. Ф."
            {
                'tier': 5,
                'desc': 'Формат "Имя О. Ф." или "Имя Ф."',
                'regex': r'\b([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ]\.)\b',
                'flags': 0
            },
        ]
    else:  # expense
        return [
            {'tier': 1, 'desc': 'Название в кавычках: «ООО Ромашка»', 'regex': r'[«"]([^»"]{3,})[»"]', 'flags': 0},
            {'tier': 1, 'desc': 'Ключ "Получатель", "Продавец", "Организация"', 'regex': fr'(?:Получатель|Продавец|Поставщик|Организация)\s*[:\s]*\n?\s*{AUTHOR_NAME_REGEX}(?=\n|$)', 'flags': re.IGNORECASE},
            {'tier': 2, 'desc': 'Орг. форма: ООО, ИП, АО, ПАО', 'regex': r'\b(?:ООО|ИП|АО|ПАО|ЗАО|ОАО)\s+[«"]?([^»"\n]{3,40})[»"]?', 'flags': re.IGNORECASE},
            {'tier': 4, 'desc': 'Английские термины: "Merchant", "To"', 'regex': fr'(?:Merchant|To)\s*[:\s]*\n?\s*{AUTHOR_NAME_REGEX}(?=\n|$)', 'flags': re.IGNORECASE},
            {'tier': 5, 'desc': 'Первая непустая строка документа', 'regex': r'^\s*([А-ЯЁа-яёA-Za-z\s«»"-]{4,40}?)\s*$', 'flags': re.MULTILINE},
            {'tier': 5, 'desc': 'Слово из заглавных букв (бренд/сеть)', 'regex': r'\b([А-ЯЁ]{3,20})\b', 'flags': 0},
        ]

# Остальные функции _get_..._patterns без изменений...
def _get_comment_patterns() -> list:
    """Возвращает шаблоны для поиска КОММЕНТАРИЯ."""
    return [{'tier': 1, 'desc': 'Поиск по ключевым словам', 'regex': r'(?:Комментарий|Примечание|Назначение\sплатежа|Note|Comment|Description)\s*[:\s]*\n?\s*(.+?)(?=\n\n|$|\n\s*—{3,})', 'flags': re.IGNORECASE | re.DOTALL}]

def _get_procedure_patterns() -> list:
    """Возвращает шаблоны для поиска ПРОЦЕДУРЫ/УСЛУГИ (для расходов)."""
    return [{'tier': 1, 'desc': 'Блок текста между "Наименование" и "Итого"', 'regex': r'(?:Наименование|Описание\sуслуг|Состав\sчека|Услуги)\s*\n(.*?)(?=\n\s*(?:Итого|Всего|Сумма|Продавец))', 'flags': re.DOTALL | re.IGNORECASE}, {'tier': 5, 'desc': 'Строка, содержащая буквы, но не ключевое слово', 'regex': r'^\s*([А-Яа-я\s]{5,50})\s*$', 'flags': re.MULTILINE | re.IGNORECASE}]

# ============================================================================
# ОСНОВНЫЕ ФУНКЦИИ ПАРСИНГА
# ============================================================================

def parse_date(text: str) -> str | None:
    """Ищет ДАТУ и нормализует к виду ДД.ММ.ГГГГ."""
    patterns = _get_date_patterns()
    # Словарь для преобразования месяцев из текста в число
    MONTHS = {'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04', 'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08', 'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12'}

    for p in patterns:
        match = re.search(p['regex'], text, p['flags'])
        if match:
            try:
                if p.get('type') == 'textual':
                    # ОБНОВЛЕННАЯ ЛОГИКА: обработка текстовой даты
                    day, month_name, year = match.groups()
                    month = MONTHS.get(month_name.lower())
                    if not month: continue
                    # Форматируем дату в стандартный вид
                    dt_obj = datetime.strptime(f"{day}.{month}.{year}", "%d.%m.%Y")
                else: # numeric
                    date_str = match.group(1).replace('/', '.').replace('-', '.')
                    parts = date_str.split('.')
                    year_format = "%Y" if len(parts[2]) == 4 else "%y"
                    dt_obj = datetime.strptime(date_str, f"%d.%m.{year_format}")

                normalized_date = dt_obj.strftime("%d.%m.%Y")
                logger.info(f"✅ Дата найдена (Уровень {p['tier']}: '{p['desc']}') | Результат: {normalized_date}")
                return normalized_date
            except (ValueError, IndexError) as e:
                logger.warning(f"⚠️ Ошибка парсинга даты: {match.group(0)} | {e}")
                continue
    logger.warning("❌ Дата не найдена в тексте")
    return None

# Функции parse_amount, parse_bank, parse_author и другие остаются почти без изменений,
# так как основная логика поиска уже заложена в иерархию шаблонов.

def parse_amount(text: str, transaction_type: str) -> float | None:
    """Ищет СУММУ в тексте, используя иерархический поиск."""
    patterns = _get_amount_patterns()
    for p in patterns:
        match = re.search(p['regex'], text, p['flags'])
        if match:
            amount_str = match.groups()[-1]
            amount = _clean_amount_string(amount_str)
            if amount and amount > 0:
                logger.info(f"✅ Сумма найдена | Уровень {p['tier']} ('{p['desc']}') | Результат: {amount}")
                return amount
    logger.warning(f"❌ Не удалось найти сумму (тип: {transaction_type})")
    return None

def parse_bank(text: str) -> str | None:
    """Ищет название БАНКА по ключевым словам."""
    patterns = _get_bank_patterns()
    search_text = text.lower()
    for p in patterns:
        if re.search(p['regex'], search_text, p['flags']):
            bank_name = p['bank_name']
            logger.info(f"✅ Банк найден | Уровень {p['tier']} ('{p['desc']}') | Результат: {bank_name}")
            return bank_name
    logger.debug("❌ Банк не найден по ключевым словам")
    return None

def parse_author(text: str, transaction_type: str) -> str | None:
    """Ищет АВТОРА транзакции."""
    patterns = _get_author_patterns(transaction_type)
    STOPWORDS = ['улица', 'москва', 'россия', 'кассир', 'чек', 'документ',
                 'операция', 'платеж', 'карта', 'счет', 'transaction', 'успешно']
    for p in patterns:
        matches = list(re.finditer(p['regex'], text, p['flags']))
        for match in matches:
            author = ' '.join(filter(None, match.groups())).strip()
            author = _clean_author_string(author)
            if len(author) < 2 or len(author) > 50: continue
            if any(stop in author.lower() for stop in STOPWORDS): continue
            if re.fullmatch(r'[\d\s.,]+', author): continue
            logger.info(f"✅ Автор найден | Уровень {p['tier']} ('{p['desc']}') | Результат: '{author}'")
            return author
    logger.warning(f"❌ Не удалось найти автора (тип: {transaction_type})")
    return None

def parse_comment(text: str) -> str | None:
    """Ищет КОММЕНТАРИЙ в тексте."""
    patterns = _get_comment_patterns()
    for p in patterns:
        match = re.search(p['regex'], text, p['flags'])
        if match:
            comment = match.group(1).strip().replace('\n', ' ')
            if len(comment) > 2:
                comment = comment[:200] + '...' if len(comment) > 200 else comment
                logger.info(f"✅ Комментарий найден | Уровень {p['tier']} ('{p['desc']}') | Результат: '{comment}'")
                return comment
    logger.debug("❌ Комментарий не найден")
    return None

def parse_procedure(text: str) -> str | None:
    """Ищет наименование ПРОЦЕДУРЫ/УСЛУГИ в чеке (для расходов)."""
    patterns = _get_procedure_patterns()
    for p in patterns:
        match = re.search(p['regex'], text, p['flags'])
        if match:
            lines = [re.sub(r'[\d,.\s]+(?:Р|₽|руб\.?)$', '', line).strip() for line in match.group(1).strip().split('\n')]
            clean_lines = [line for line in lines if len(line) > 2]
            if clean_lines:
                result = '; '.join(clean_lines)
                logger.info(f"✅ Процедура найдена | Уровень {p['tier']} ('{p['desc']}') | Результат: '{result}'")
                return result
    logger.debug("❌ Процедура/услуга не найдена")
    return None

# ============================================================================
# ГЛАВНАЯ ФУНКЦИЯ - ТОЧКА ВХОДА
# ============================================================================

def parse_transaction_data(text: str, transaction_type: str) -> dict:
    """Главная функция парсинга."""
    logger.info(f"🔍 Начинаем парсинг. Тип: {transaction_type.upper()}. Объем текста: {len(text)} символов.")
    normalized_text = _normalize_text_for_search(text)
    
    result = {
        "date": parse_date(normalized_text),
        "amount": parse_amount(normalized_text, transaction_type),
    }

    if transaction_type == 'income':
        result['bank'] = parse_bank(normalized_text)
        result['author'] = parse_author(normalized_text, transaction_type)
        result['comment'] = parse_comment(normalized_text)
    else:  # expense
        result['procedure'] = parse_procedure(normalized_text)
        result['author'] = parse_author(normalized_text, transaction_type)
        result['comment'] = parse_comment(normalized_text)

    filled_fields = sum(1 for v in result.values() if v is not None)
    total_fields = len(result)
    logger.info(
        f"📊 Парсинг завершен. "
        f"Распознано полей: {filled_fields}/{total_fields}. "
        f"Итог: {result}"
    )
    return result