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
        {'tier': 3, 'desc': 'Любая дата в числовом формате (ДД.ММ.ГГГГ)', 'regex': r'\b(\d{2}[./-]\d{2}[./-]\d{2,4})\b', 'type': 'numeric', 'flags': 0}
    ]

def _get_amount_patterns() -> list:
    AMOUNT_REGEX = r'(\d(?:\s?\d)*(?:[,.]\d{1,2})?)'
    CURRENCY_REGEX = r'(?:Р|₽|руб\.?|RUB|P)'
    return [
        {'tier': 0, 'desc': 'Ключевое слово "Итого сумма чека"', 'regex': fr'(?:Итого\sсумма\sчека)\s*[:\s.]*\s*{AMOUNT_REGEX}', 'flags': re.IGNORECASE},
        {'tier': 2, 'desc': 'Ключевое слово "Сумма/Итого/Всего/Долг"', 'regex': fr'(?:Сумма|Итого|Всего|К\sоплате|Пополнение|Перевод|Долг\sпосле\sоплаты)\s*[:\s.]*\s*{AMOUNT_REGEX}', 'flags': re.IGNORECASE},
        {'tier': 4, 'desc': 'Число с явным символом валюты', 'regex': fr'\b{AMOUNT_REGEX}\s*{CURRENCY_REGEX}\b', 'flags': re.IGNORECASE},
    ]

def _get_bank_patterns() -> list:
    BANK_KEYWORDS = {'Т-Банк': ['т-банк', 'тбанк', 'тинькофф', 'tinkoff', 't-bank'], 'Сбербанк': ['сбербанк', 'сбер', 'sber', 'sberbank'], 'Альфа-Банк': ['альфа-банк', 'альфа', 'alfa', 'alfabank']}
    return [{'tier': 1, 'regex': r'\b(' + '|'.join(keywords) + r')\b', 'bank_name': bank_name, 'flags': re.IGNORECASE} for bank_name, keywords in BANK_KEYWORDS.items()]

def _get_author_patterns(transaction_type: str) -> list:
    AUTHOR_NAME_REGEX = r'([А-ЯЁ][а-яёA-Za-z\s."«»-]+?)'
    if transaction_type in ['income', 'transaction']:
        return [{'tier': 5, 'desc': 'Формат "Имя О." или "Имя Отчество О."', 'regex': r'\b([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){0,2}\s+[А-ЯЁ]\.)\b', 'flags': 0}]
    else:
        return [{'tier': 2, 'desc': 'Орг. форма: ООО, ИП, АО', 'regex': r'\b(?:ООО|ИП|АО|ПАО)\s+[«"]?([^»"\n]{3,40})[»"]?', 'flags': re.IGNORECASE}]

def _get_comment_patterns() -> list:
    return [{'tier': 1, 'regex': r'(?:Комментарий|Примечание|Назначение)\s*[:\s\n]*(.+?)(?=\n\n|$)', 'flags': re.IGNORECASE | re.DOTALL}]

def _get_procedure_patterns() -> list:
    return [{'tier': 1, 'regex': r'(?:Наименование.*?Ст-ть)\s*\n(.*?)(?=\n\s*Итого)', 'flags': re.DOTALL | re.IGNORECASE}]

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
    for p in _get_bank_patterns():
        if re.search(p['regex'], text.lower(), p['flags']): return p['bank_name']
    return None

def parse_author(text: str, transaction_type: str) -> str | None:
    for p in _get_author_patterns(transaction_type):
        for match in re.finditer(p['regex'], text, p['flags']):
            author = _clean_author_string(match.group(1))
            if len(author) > 2: return author
    return None

def parse_comment(text: str) -> str | None:
    if match := re.search(_get_comment_patterns()[0]['regex'], text, _get_comment_patterns()[0]['flags']):
        return match.group(1).strip().replace('\n', ' ')
    return None

def parse_procedure(text: str) -> str | None:
    if match := re.search(_get_procedure_patterns()[0]['regex'], text, _get_procedure_patterns()[0]['flags']):
        lines = [re.sub(r'[\s\d,.]+(руб\.?)?$', '', l).strip() for l in match.group(1).strip().split('\n') if l.strip()]
        return '; '.join(lines)
    return None

def _parse_multiple_transactions(text: str) -> dict:
    result = {}
    date_match = re.search(r'([A-Za-z]{3,}\s\d{4})', text)
    result['period'] = date_match.group(1) if date_match else "не найден"
    income_match = re.search(r'([\d\s,.]+\s*Р)\s*\n\s*Income', text, re.IGNORECASE)
    result['total_income'] = income_match.group(1).strip() if income_match else "не найден"
    
    transactions = []
    pattern = re.compile(r'([А-ЯЁа-яё\s]+\s[А-ЯЁ]\.)\s*\n([\s\S]*?)(?=(?:[А-ЯЁа-яё\s]+\s[А-ЯЁ]\.)|$)')
    for match in pattern.finditer(text):
        sender, block = match.group(1).strip(), match.group(2)
        tx_data = {'sender': sender}
        if amount_match := re.search(r'(\+\s*[\d\s,.]+\s*Р)', block):
            tx_data['amount_str'] = amount_match.group(1).strip()
            tx_data['amount'] = _clean_amount_string(amount_match.group(1))
        if type_match := re.search(r'(Transfers|Top-ups)', block, re.IGNORECASE):
            tx_data['type'] = 'Перевод' if type_match.group(1).lower() == 'transfers' else 'Пополнение'
        if card_match := re.search(r'(Black)', block, re.IGNORECASE):
            tx_data['card'] = card_match.group(1)
        
        lines = [line.strip() for line in block.strip().split('\n')]
        tags = [line for line in lines if re.match(r'^[А-ЯЁа-яё]+$', line) and line not in (tx_data.get('type'), tx_data.get('card'))]
        if tags: tx_data['tag'] = ', '.join(tags)
        
        if tx_data.get('amount'): transactions.append(tx_data)
    result['transactions'] = transactions
    return result

def parse_transaction_data(text: str, transaction_type: str) -> dict:
    logger.info(f"Начинаем парсинг. Тип: {transaction_type.upper()}.")
    if transaction_type == 'transaction':
        parsed_details = _parse_multiple_transactions(text)
        result = {"bank": parse_bank(text), **parsed_details}
    else:
        normalized_text = _normalize_text_for_search(text)
        result = {
            "date": parse_date(text), "amount": parse_amount(text, transaction_type),
            "author": parse_author(normalized_text, transaction_type), "comment": parse_comment(normalized_text),
        }
        if transaction_type == 'income':
            result['bank'] = parse_bank(normalized_text)
        else:
            result['procedure'] = parse_procedure(text)
    logger.info(f"Парсинг завершен. Итог: {result}")
    return result