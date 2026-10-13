"""QIF, the format Quicken made and many banks still offer."""

import re
from datetime import date

AMOUNT_CLEANUP = re.compile(r'[^\d,.\-]')


def _decode(data):
    for encoding in ('utf-8', 'latin-1'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='replace')


def _parse_amount(value):
    value = AMOUNT_CLEANUP.sub('', value or '').strip()
    if not value:
        raise ValueError('An amount of the QIF file is empty.')
    # a comma is the decimal separator when no dot follows it, a thousands separator otherwise
    if ',' in value and '.' in value:
        value = value.replace(',', '') if value.index(',') < value.index('.') else \
            value.replace('.', '').replace(',', '.')
    elif ',' in value:
        value = value.replace(',', '.') if len(value.split(',')[-1]) != 3 else value.replace(',', '')
    return float(value)


def _parse_date(value, date_format=None):
    value = (value or '').strip().replace("'", '/').replace('-', '/').replace('.', '/')
    # Quicken writes the day of a month before the 10th as " 1"
    parts = [part.strip() for part in value.split('/') if part.strip()]
    if len(parts) != 3:
        raise ValueError(f'The date {value!r} of the QIF file cannot be read.')
    if date_format:
        order = [{'%d': 'day', '%m': 'month', '%y': 'year', '%Y': 'year'}[directive]
                 for directive in re.findall(r'%[dmyY]', date_format)]
    else:
        # a day above 12 tells the two apart; the American order is the default of the format
        first, second = int(parts[0]), int(parts[1])
        order = ['day', 'month', 'year'] if first > 12 or (second <= 12 < first) else ['month', 'day', 'year']
    values = dict(zip(order, (int(part) for part in parts)))
    year = values['year']
    if year < 100:
        year += 2000 if year < 70 else 1900
    return date(year, values['month'], values['day'])


def parse(data, filename, options=None):
    text = _decode(data)
    if '!Type' not in text and not text.lstrip().startswith('!'):
        return None
    if not re.search(r'!Type:\s*(Bank|CCard|Cash|Oth\s*[AL])', text, re.IGNORECASE):
        return None

    options = options or {}
    date_format = options.get('date_format')
    transactions = []
    values = {}
    account_number = None
    in_account = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip('\r')
        if not line:
            continue
        if line.startswith('!'):
            in_account = line.lower().startswith('!account')
            continue
        code, content = line[0], line[1:].strip()
        if line.startswith('^'):
            if in_account:
                account_number = values.get('number') or account_number
            elif values.get('date') and values.get('amount') is not None:
                transactions.append(values)
            values = {}
            continue
        if in_account:
            if code == 'N':
                values['number'] = content
            continue
        if code == 'D':
            values['date'] = _parse_date(content, date_format)
        elif code == 'T' or (code == 'U' and 'amount' not in values):
            values['amount'] = _parse_amount(content)
        elif code == 'P':
            values['payment_ref'] = content
        elif code == 'M':
            values['narration'] = content
        elif code == 'N':
            values['ref'] = content
        elif code == 'L':
            values.setdefault('narration', content)

    if not transactions:
        raise ValueError('This QIF file holds no transaction.')
    for index, values in enumerate(transactions):
        label = values.pop('payment_ref', None) or values.get('narration') or values.get('ref') or ''
        values.update({
            'payment_ref': label or f"{values['date']} {values['amount']}",
            'partner_name': label or None,
            # a QIF transaction has no identifier: its place in the file tells two identical ones apart
            'unique_import_id': f"{values['date']}-{values['amount']}-{index}",
        })
    return [{
        'name': None,
        'date': max(values['date'] for values in transactions),
        'balance_start': None,
        'balance_end_real': None,
        'currency_code': None,
        'account_number': account_number,
        'transactions': transactions,
    }]
