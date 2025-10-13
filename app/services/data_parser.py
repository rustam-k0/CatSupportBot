import re
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def _clean_amount_string(s: str) -> float | None:
    if not isinstance(s, str): return None
    try:
        cleaned = re.sub(r'[^\d,.]', '', s).replace(',', '.')
        return float(cleaned)
    except (ValueError, TypeError): return None

def _normalize_text_for_search(text: str) -> str:
    if not isinstance(text, str): return ''
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

def _clean_author_string(author: str) -> str:
    author = author.strip('.,;:"«» \n\t')
    author = re.sub(r'^(ООО|ИП|АО|ПАО|ЗАО|ОАО)\s+', '', author, flags=re.IGNORECASE).strip()
    return author.strip('"«»')

def _get_date_patterns() -> list:
    return [
        {'tier': 0, 'desc': 'Дата операции с временем (текстовая, с ключом)', 'regex': r'(?:Операция\s+совершена|Дата\s+операции|Товарный\sчек\s.*?за)[:\s]*(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})', 'type': 'textual_ru', 'flags': re.IGNORECASE},
        {'tier': 0, 'desc': 'Дата операции с временем (числовая, с ключом)', 'regex': r'(?:Операция\s+совершена|Дата\s+операции)[:\s]*(\d{2}[./-]\d{2}[./-]\d{2,4})(?:\s+в\s+\d{1,2}:\d{2})?', 'type': 'numeric', 'flags': re.IGNORECASE},
        {'tier': 1, 'desc': 'Дата рядом с суммой или переводом', 'regex': r'(?:Перевод|Зачисление|Списание)\s+от?\s*(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})', 'type': 'textual_ru', 'flags': re.IGNORECASE},
        {'tier': 1, 'desc': 'Дата рядом с суммой или переводом (числовая)', 'regex': r'(?:Перевод|Зачисление|Списание)\s+от?\s*(\d{2}[./-]\d{2}[./-]\d{2,4})', 'type': 'numeric', 'flags': re.IGNORECASE},
        {'tier': 3, 'desc': 'Любая дата в числовом формате (ДД.ММ.ГГГГ)', 'regex': r'\b(\d{2}[./-]\d{2}[./-]\d{2,4})\b', 'type': 'numeric', 'flags': 0}
    ]

def _get_amount_patterns() -> list:
    AMOUNT_REGEX = r'(\d(?:\s?\d)*(?:[,.]\d{1,2})?)'
    CURRENCY_REGEX = r'(?:Р|₽|руб\.?|RUB|P)'
    return [
        {'tier': 0, 'desc': 'Ключевое слово "Итого сумма чека"', 'regex': fr'(?:Итого\sсумма\sчека)\s*[:\s.]*\s*{AMOUNT_REGEX}', 'flags': re.IGNORECASE},
        {'tier': 1, 'desc': 'Сумма с явным знаком "+" и символом валюты', 'regex': fr'\+\s*{AMOUNT_REGEX}\s*{CURRENCY_REGEX}', 'flags': re.IGNORECASE},
        {'tier': 2, 'desc': 'Ключевое слово "Сумма/Итого/Всего/Долг"', 'regex': fr'(?:Сумма|Итого|Всего|К\sоплате|Пополнение|Перевод|Долг\sпосле\sоплаты)\s*[:\s.]*\s*{AMOUNT_REGEX}', 'flags': re.IGNORECASE},
        {'tier': 4, 'desc': 'Число с явным символом валюты', 'regex': fr'\b{AMOUNT_REGEX}\s*{CURRENCY_REGEX}\b', 'flags': re.IGNORECASE},
        {'tier': 5, 'desc': 'Число с копейками (формат: 1234.56)', 'regex': r'\b(\d(?:\s?\d)*[,.]\d{2})\b', 'flags': 0},
    ]

def _get_bank_patterns() -> list:
    BANK_KEYWORDS = {'Т-Банк': ['т-банк', 'тбанк', 'тинькофф', 'tinkoff', 't-bank'], 'Сбербанк': ['сбербанк', 'сбер', 'sber', 'sberbank'], 'Альфа-Банк': ['альфа-банк', 'альфа', 'alfa', 'alfabank'], 'ВТБ': ['втб', 'vtb']}
    return [{'tier': 1, 'desc': f'Поиск по ключевым словам для "{bank_name}"', 'regex': r'\b(' + '|'.join(keywords) + r')\b', 'bank_name': bank_name, 'flags': re.IGNORECASE} for bank_name, keywords in BANK_KEYWORDS.items()]

def _get_author_patterns(transaction_type: str) -> list:
    AUTHOR_NAME_REGEX = r'([А-ЯЁ][а-яёA-Za-z\s."«»-]+?)'
    if transaction_type in ['income', 'transaction']:
        return [
            {'tier': 1, 'desc': 'Ключ "Отправитель", "Плательщик", "От кого"', 'regex': fr'(?:Отправитель|Плательщик|От\sкого)\s*[:\s\n]*{AUTHOR_NAME_REGEX}(?=\n|$)', 'flags': re.IGNORECASE},
            {'tier': 3, 'desc': 'Имя формата (Имя О.) после строки с суммой', 'regex': r'\b(?:\d[\d\s,.]*)\s*(?:Р|₽|руб\.?|RUB|P)[\s\n]+([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ]\.)', 'flags': re.IGNORECASE},
            {'tier': 5, 'desc': 'Формат "Имя О." или "Имя Отчество О."', 'regex': r'\b([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){0,2}\s+[А-ЯЁ]\.)\b', 'flags': 0},
        ]
    else:
        return [
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
    for p in patterns:
        for match in re.finditer(p['regex'], text, p['flags']):
            try:
                dt_obj = None
                if p.get('type') == 'textual_ru':
                    day, month_name, year = match.groups()
                    dt_obj = datetime.strptime(f"{day}.{MONTHS_RU[month_name.lower()]}.{year}", "%d.%m.%Y")
                elif p.get('type') == 'numeric':
                    date_str = match.group(1).replace('/', '.').replace('-', '.')
                    year_format = "%Y" if len(date_str.split('.')[2]) == 4 else "%y"
                    dt_obj = datetime.strptime(date_str, f"%d.%m.{year_format}")
                if dt_obj: return dt_obj.strftime("%d.%m.%Y")
            except (ValueError, IndexError): continue
    return None

def parse_amount(text: str, transaction_type: str) -> float | None:
    for p in _get_amount_patterns():
        if match := re.search(p['regex'], text, p['flags']):
            if amount := _clean_amount_string(match.groups()[-1]): return amount
    return None

def parse_bank(text: str) -> str | None:
    search_text = text.lower()
    for p in _get_bank_patterns():
        if re.search(p['regex'], search_text, p['flags']): return p['bank_name']
    return None

def parse_author(text: str, transaction_type: str) -> str | None:
    STOPWORDS = ['улица', 'москва', 'россия', 'кассир', 'чек', 'операция', 'платеж', 'карта', 'счет']
    for p in _get_author_patterns(transaction_type):
        for match in re.finditer(p['regex'], text, p['flags']):
            author = _clean_author_string(' '.join(filter(None, match.groups())).strip())
            if 2 < len(author) < 50 and not any(stop in author.lower() for stop in STOPWORDS) and not re.fullmatch(r'[\d\s.,]+', author):
                return author
    return None

def parse_comment(text: str) -> str | None:
    for p in _get_comment_patterns():
        if match := re.search(p['regex'], text, p['flags']):
            comment = match.group(1).strip().replace('\n', ' ')
            if len(comment) > 2: return comment[:200]
    return None

def parse_procedure(text: str) -> str | None:
    for p in _get_procedure_patterns():
        if match := re.search(p['regex'], text, p['flags']):
            lines = [re.sub(r'[\s\d,.]+(руб\.?)?$', '', line).strip() for line in match.group(1).strip().split('\n') if line.strip()]
            if clean_lines := [re.sub(r'\s*\([^)]*\)', '', l).strip() for l in lines if len(l) > 2 and re.search(r'[а-яА-Я]', l)]:
                return '; '.join(clean_lines)
    return None

def _parse_multiple_transactions(text: str) -> list[dict]:
    pattern = re.compile(r'([А-ЯЁа-яё\s]+\s[А-ЯЁ]\.)\n(?:Transfers|Top-ups).*?\+\s*([\d\s,.]+)\s*Р', re.MULTILINE)
    transactions = []
    for match in pattern.finditer(text):
        author, amount_str = match.groups()
        if (amount := _clean_amount_string(amount_str)):
            transactions.append({'author': author.strip(), 'amount': amount})
    return transactions

def parse_transaction_data(text: str, transaction_type: str) -> dict:
    logger.info(f"🔍 Начинаем парсинг. Тип: {transaction_type.upper()}. Объем текста: {len(text)} символов.")
    normalized_text = _normalize_text_for_search(text)
    
    if transaction_type == 'transaction':
        result = {
            "transactions": _parse_multiple_transactions(normalized_text),
            "bank": parse_bank(normalized_text),
            "comment": parse_comment(normalized_text)
        }
    else:
        result = {
            "date": parse_date(text),
            "amount": parse_amount(text, transaction_type),
            "author": parse_author(normalized_text, transaction_type),
            "comment": parse_comment(normalized_text),
        }
        if transaction_type == 'income':
            result['bank'] = parse_bank(normalized_text)
        else:
            result['procedure'] = parse_procedure(text)
    
    logger.info(f"📊 Парсинг завершен. Итог: {result}")
    return result