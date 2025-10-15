import re
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def _clean_amount_string(s: str) -> float | None:
    if not isinstance(s, str):
        return None
    try:
        # Удаляем все, кроме цифр, запятых и точек. Пробелы тоже убираем.
        cleaned = re.sub(r'[^\d,.]', '', s)
        # Заменяем запятую на точку для корректного преобразования в float
        cleaned = cleaned.replace(',', '.')
        return float(cleaned)
    except (ValueError, TypeError):
        return None

def _normalize_text_for_search(text: str) -> str:
    if not isinstance(text, str):
        return ''
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

def _clean_author_string(author: str) -> str:
    author = author.strip('.,;:"«» \n\t')
    author = re.sub(r'^(ООО|ИП|АО|ПАО|ЗАО|ОАО)\s+', '', author, flags=re.IGNORECASE).strip()
    author = author.strip('"«»')
    # Добавляем точку в конце, если ее нет, для унификации
    if not author.endswith('.'):
        author += '.'
    return author

def _get_date_patterns() -> list:
    return [
        {
            'tier': 0,
            'desc': 'Дата операции с временем (текстовая, с ключом)',
            'regex': r'(?:Операция\s+совершена|Дата\s+операции|Товарный\sчек\s.*?за)[:\s]*(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})',
            'type': 'textual_ru',
            'flags': re.IGNORECASE
        },
        {
            'tier': 0,
            'desc': 'Дата операции с временем (числовая, с ключом)',
            'regex': r'(?:Операция\s+совершена|Дата\s+операции)[:\s]*(\d{2}[./-]\d{2}[./-]\d{2,4})(?:\s+в\s+\d{1,2}:\d{2})?',
            'type': 'numeric',
            'flags': re.IGNORECASE
        },
        {
            'tier': 1,
            'desc': 'Дата рядом с суммой или переводом',
            'regex': r'(?:Перевод|Зачисление|Списание)\s+от?\s*(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})',
            'type': 'textual_ru',
            'flags': re.IGNORECASE
        },
        {
            'tier': 1,
            'desc': 'Дата рядом с суммой или переводом (числовая)',
            'regex': r'(?:Перевод|Зачисление|Списание)\s+от?\s*(\d{2}[./-]\d{2}[./-]\d{2,4})',
            'type': 'numeric',
            'flags': re.IGNORECASE
        },
        {
            'tier': 2,
            'desc': 'Английская дата с разделителем и временем',
            'regex': r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s*[•\-]\s*\d{1,2}:\d{2}',
            'type': 'textual_en',
            'flags': re.IGNORECASE
        },
        {
            'tier': 2,
            'desc': 'Английская дата с пробелом и временем',
            'regex': r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}:\d{2}',
            'type': 'textual_en',
            'flags': re.IGNORECASE
        },
        {
            'tier': 3,
            'desc': 'Любая дата в числовом формате (ДД.ММ.ГГГГ)',
            'regex': r'\b(\d{2}[./-]\d{2}[./-]\d{2,4})\b',
            'type': 'numeric',
            'flags': 0
        },
        {
            'tier': 4,
            'desc': 'Любая дата в текстовом формате (8 октября 2025)',
            'regex': r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})\b',
            'type': 'textual_ru',
            'flags': re.IGNORECASE
        },
        {
            'tier': 5,
            'desc': 'Английская дата без времени',
            'regex': r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b',
            'type': 'textual_en',
            'flags': re.IGNORECASE
        },
        {
            'tier': 6,
            'desc': 'Дата формирования документа',
            'regex': r'(?:Сформировано|Создано|Дата\s+формирования).*?(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})',
            'type': 'textual_ru',
            'flags': re.IGNORECASE | re.DOTALL
        },
    ]

def _get_amount_patterns() -> list:
    AMOUNT_REGEX = r'(\d(?:\s?\d)*(?:[,.]\d{1,2})?)'
    CURRENCY_REGEX = r'(?:Р|₽|руб\.?|RUB|P)'

    return [
        {'tier': 0, 'desc': 'Ключевое слово "Итого сумма чека"', 'regex': fr'(?:Итого\sсумма\sчека)\s*[:\s.]*\s*{AMOUNT_REGEX}', 'flags': re.IGNORECASE},
        {'tier': 1, 'desc': 'Сумма с явным знаком "+" и символом валюты', 'regex': fr'\+\s*{AMOUNT_REGEX}\s*{CURRENCY_REGEX}', 'flags': re.IGNORECASE},
        {'tier': 2, 'desc': 'Ключевое слово "Сумма/Итого/Всего/Долг" и число', 'regex': fr'(?:Сумма|Итого|Всего|К\sоплате|Пополнение|Перевод|Долг\sпосле\sоплаты)\s*[:\s.]*\s*{AMOUNT_REGEX}', 'flags': re.IGNORECASE},
        {'tier': 3, 'desc': 'Ключевое слово на отдельной строке ВЫШЕ числа', 'regex': fr'(?:Сумма|Итого|Всего|Операция|Сумма\sв\sвалюте\sоперации)\s*\n+\s*{AMOUNT_REGEX}\s*{CURRENCY_REGEX}?', 'flags': re.IGNORECASE},
        {'tier': 4, 'desc': 'Число с явным символом валюты', 'regex': fr'\b{AMOUNT_REGEX}\s*{CURRENCY_REGEX}\b', 'flags': re.IGNORECASE},
        {'tier': 5, 'desc': 'Число с копейками (формат: 1234.56)', 'regex': r'\b(\d(?:\s?\d)*[,.]\d{2})\b', 'flags': 0},
    ]

def _get_bank_patterns() -> list:
    BANK_KEYWORDS = {
        'Т-Банк': ['т-банк', 'тбанк', 'тинькофф', 'tinkoff', 't-bank'],
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
    AUTHOR_NAME_REGEX = r'([А-ЯЁ][а-яёA-Za-z\s."«»-]+?)'

    if transaction_type in ['income', 'transaction']:
        return [
            {'tier': 1, 'desc': 'Ключ "Отправитель", "Плательщик", "От кого"', 'regex': fr'(?:Отправитель|Плательщик|От\sкого)\s*[:\s\n]*{AUTHOR_NAME_REGEX}(?=\n|$)', 'flags': re.IGNORECASE},
            {'tier': 2, 'desc': 'Имя после слова "Описание"', 'regex': r'Описание[\s\n]+([А-ЯЁа-яё\s]+\s[А-ЯЁ]\.)', 'flags': re.IGNORECASE},
            {'tier': 3, 'desc': 'Имя формата (Имя О.) после строки с суммой', 'regex': r'\b(?:\d[\d\s,.]*)\s*(?:Р|₽|руб\.?|RUB|P)[\s\n]+([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ]\.)', 'flags': re.IGNORECASE},
            {'tier': 4, 'desc': 'Английские термины: "From", "Sender"', 'regex': fr'(?:From|Sender)\s*[:\s\n]*{AUTHOR_NAME_REGEX}(?=\n|$)', 'flags': re.IGNORECASE},
            {'tier': 5, 'desc': 'Формат "Имя О." или "Имя Отчество О."', 'regex': r'\b([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){0,2}\s+[А-ЯЁ]\.)\b', 'flags': 0},
        ]
    else: # expense
        return [
            {'tier': 0, 'desc': 'Название организации в начале документа (над адресом)', 'regex': r'^(.*?)\n\s*(?:Адрес\sклиники|Адрес)', 'flags': re.MULTILINE},
            {'tier': 1, 'desc': 'Название в кавычках: «ООО Ромашка»', 'regex': r'[«"]([^»"]{3,})[»"]', 'flags': 0},
            {'tier': 1, 'desc': 'Ключ "Получатель", "Продавец"', 'regex': fr'(?:Получатель|Продавец|Организация)\s*[:\s\n]*{AUTHOR_NAME_REGEX}(?=\n|$)', 'flags': re.IGNORECASE},
            {'tier': 2, 'desc': 'Орг. форма: ООО, ИП, АО', 'regex': r'\b(?:ООО|ИП|АО|ПАО)\s+[«"]?([^»"\n]{3,40})[»"]?', 'flags': re.IGNORECASE},
        ]

def _get_comment_patterns() -> list:
    return [{'tier': 1, 'desc': 'Поиск по ключевым словам', 'regex': r'(?:Комментарий|Примечание|Назначение\sплатежа|Note|Comment|Description)\s*[:\s\n]*(.+?)(?=\n\n|$|\n\s*—{3,})', 'flags': re.IGNORECASE | re.DOTALL}]

def _get_procedure_patterns() -> list:
    return [{'tier': 1, 'desc': 'Блок текста между заголовком таблицы и итоговой суммой', 'regex': r'(?:Наименование.*?Ст-ть)\s*\n(.*?)(?=\n\s*Итого\sсумма\sчека)', 'flags': re.DOTALL | re.IGNORECASE}]

def parse_date(text: str) -> str | None:
    patterns = _get_date_patterns()
    MONTHS_RU = {'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04', 'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08', 'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12'}
    MONTHS_EN = {'january': '01', 'february': '02', 'march': '03', 'april': '04', 'may': '05', 'june': '06', 'july': '07', 'august': '08', 'september': '09', 'october': '10', 'november': '11', 'december': '12'}

    found_dates = []
    
    for p in patterns:
        matches = list(re.finditer(p['regex'], text, p['flags']))
        for match in matches:
            try:
                dt_obj = None
                if p.get('type') == 'textual_ru':
                    day, month_name, year = match.groups()
                    month = MONTHS_RU.get(month_name.lower())
                    if month: 
                        dt_obj = datetime.strptime(f"{day}.{month}.{year}", "%d.%m.%Y")

                elif p.get('type') == 'textual_en':
                    day, month_name = match.groups()
                    month = MONTHS_EN.get(month_name.lower())
                    year = datetime.now().year
                    if month: 
                        dt_obj = datetime.strptime(f"{day}.{month}.{year}", "%d.%m.%Y")

                elif p.get('type') == 'numeric':
                    date_str = match.group(1).replace('/', '.').replace('-', '.')
                    parts = date_str.split('.')
                    year_format = "%Y" if len(parts[2]) == 4 else "%y"
                    dt_obj = datetime.strptime(date_str, f"%d.%m.{year_format}")

                if dt_obj:
                    normalized_date = dt_obj.strftime("%d.%m.%Y")
                    found_dates.append({
                        'date': normalized_date,
                        'tier': p['tier'],
                        'match_text': match.group(0),
                        'position': match.start()
                    })
            except (ValueError, IndexError) as e:
                continue

    if found_dates:
        best_date = min(found_dates, key=lambda x: (x['tier'], x['position']))
        return best_date['date']
    
    return None

def parse_amount(text: str, transaction_type: str) -> float | None:
    patterns = _get_amount_patterns()
    for p in patterns:
        match = re.search(p['regex'], text, p['flags'])
        if match:
            amount_str = match.groups()[-1]
            amount = _clean_amount_string(amount_str)
            if amount and amount > 0:
                return amount
    return None

def parse_bank(text: str) -> str | None:
    patterns = _get_bank_patterns()
    search_text = text.lower()
    for p in patterns:
        if re.search(p['regex'], search_text, p['flags']):
            bank_name = p['bank_name']
            return bank_name
    return None

def parse_author(text: str, transaction_type: str) -> str | None:
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
            return author
    return None

def parse_comment(text: str) -> str | None:
    patterns = _get_comment_patterns()
    for p in patterns:
        match = re.search(p['regex'], text, p['flags'])
        if match:
            comment = match.group(1).strip().replace('\n', ' ')
            if len(comment) > 2:
                comment = comment[:200] + '...' if len(comment) > 200 else comment
                return comment
    return None

def parse_procedure(text: str) -> str | None:
    patterns = _get_procedure_patterns()
    for p in patterns:
        match = re.search(p['regex'], text, p['flags'])
        if match:
            procedures_block = match.group(1).strip()
            clean_lines = []
            
            for line in procedures_block.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                cleaned_line = re.sub(r'[\s\d,.]+(руб\.?)?$', '', line).strip()
                cleaned_line = re.sub(r'\s*\([^)]*\)', '', cleaned_line).strip()
                
                if len(cleaned_line) > 2 and re.search(r'[а-яА-Я]', cleaned_line):
                    clean_lines.append(cleaned_line)
            
            if clean_lines:
                result = '; '.join(clean_lines)
                return result
    return None

def parse_multiple_transactions(text: str) -> list[dict]:
    """
    Парсит блок текста, чтобы найти несколько доходных транзакций со скриншота.
    Логика основана на построчном анализе.
    """
    logger.info(f"🔍 Начинаем парсинг множественных транзакций. Объем текста: {len(text)} символов.")
    
    bank = parse_bank(text)
    transactions = []
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    # Паттерн для поиска суммы (начинается с "+", содержит цифры, пробелы, запятые/точки и заканчивается "Р" или "₽")
    amount_pattern = re.compile(r'^\+\s*([\d\s,.]+)\s*(?:₽|Р)$')
    # Паттерн для поиска имени (Имя Фамилия/Буква. - например, "Рустам Х" или "Тамирлан Ш.")
    author_pattern = re.compile(r'^[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.?$')

    for i, line in enumerate(lines):
        amount_match = amount_pattern.search(line)
        # Если строка содержит сумму дохода
        if amount_match:
            amount_str = amount_match.group(1)
            amount = _clean_amount_string(amount_str)
            
            author = None
            # Ищем автора в предыдущих строках. На скриншотах Т-Банка он обычно на 2 строки выше.
            # Проверяем строки с i-1 по i-3, чтобы быть более гибкими к ошибкам OCR
            if i > 0:
                # В скриншоте Т-Банка имя находится через одну строку выше (i-2)
                # Пример:
                # [i-2]: Тамирлан Ш.  <- Имя
                # [i-1]: Transfers    <- Тип
                # [i]:   +200 Р       <- Сумма
                if i >= 2 and author_pattern.match(lines[i-2]):
                    author = lines[i-2]
                # Запасной вариант: ищем на строке прямо перед суммой
                elif author_pattern.match(lines[i-1]):
                     author = lines[i-1]


            if author and amount:
                transactions.append({
                    'author': _clean_author_string(author),
                    'amount': amount,
                    'bank': bank if bank else "Не определен"
                })

    logger.info(f"📊 Парсинг множественных транзакций завершен. Распознано: {len(transactions)} записей.")
    return transactions


def parse_transaction_data(text: str, transaction_type: str) -> dict:
    logger.info(f"🔍 Начинаем парсинг. Тип: {transaction_type.upper()}. Объем текста: {len(text)} символов.")
    
    result = {
        "date": parse_date(text),
        "amount": parse_amount(text, transaction_type),
    }

    if transaction_type in ['income', 'transaction']:
        normalized_text = _normalize_text_for_search(text)
        result['bank'] = parse_bank(normalized_text)
        result['author'] = parse_author(normalized_text, transaction_type)
        result['comment'] = parse_comment(normalized_text)
    else: # expense
        result['procedure'] = parse_procedure(text)
        result['author'] = parse_author(text, transaction_type)
        result['comment'] = parse_comment(text)

    filled_fields = sum(1 for v in result.values() if v is not None)
    total_fields = len(result)
    logger.info(
        f"📊 Парсинг завершен. "
        f"Распознано полей: {filled_fields}/{total_fields}. "
        f"Итог: {result}"
    )
    return result