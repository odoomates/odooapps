"""MT940 files, the SWIFT statements, in their common variants.

A file is a list of ``:xx:`` tags, a statement starting at each ``:20:``. The layout of the ``:86:``
information is left free by the standard, the three shapes the banks use are recognised here: the
``/NAME/`` subfields of the SEPA banks, the ``?20`` subfields of the German and Dutch ones, and free text.
"""

import re
from datetime import date, timedelta

# :61:  value date, entry date, mark, amount, transaction type, customer reference // bank reference
LINE = re.compile(r"""
    ^(?P<value_date>\d{6})
    (?P<entry_date>\d{4})?
    (?P<mark>RC|RD|C|D)
    (?P<funds_code>[A-Z])?
    (?P<amount>[\d.,]+)
    (?P<transaction_type>N.{3})?
    (?P<references>.*)
""", re.VERBOSE | re.DOTALL)

# :60F: and :62F:  mark, date, currency, amount
BALANCE = re.compile(r'^(?P<mark>[CD])(?P<date>\d{6})(?P<currency>[A-Z]{3})(?P<amount>[\d.,]+)')

TAG = re.compile(r'^:(\d{2}[A-Z]?):(.*)$')

BIC = re.compile(r'^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$')

# The subfields of a :86: of the SEPA banks, the ones that are not listed here are kept in the narration.
SLASH_FIELDS = (
    'ACCT', 'ADDR', 'BENM', 'BIC', 'CDTRREF', 'CNTP', 'CREF', 'CSID', 'EREF', 'IBAN', 'ID', 'ISDT',
    'MARF', 'NAME', 'ORDP', 'PREF', 'PURP', 'REMI', 'RTRN', 'RMTINF', 'ULTB', 'ULTD',
)
SLASH_FIELD = re.compile(r'/(%s)/' % '|'.join(SLASH_FIELDS))

# The subfields of a :86: of the German and Dutch banks: ?20 to ?29 and ?60 to ?63 are the description,
# ?30 the bank of the other party, ?31 its account and ?32/?33 its name.
SUBFIELD = re.compile(r'\?(\d{2})([^?]*)')
DESCRIPTION_SUBFIELDS = tuple('%02d' % index for index in list(range(20, 30)) + list(range(60, 64)))

# The references the banks send when there is none.
EMPTY_REFERENCES = ('NONREF', 'NOTPROVIDED', 'UNKNOWN')


def parse(data, filename, options=None):
    text = _decode(data) if isinstance(data, (bytes, bytearray)) else data
    text = _unwrap(text)
    if ':20:' not in text or ':61:' not in text:
        return None
    statements = []
    statement = transaction = None
    for tag, value in _tags(text):
        if tag == '20':
            statement = _new_statement(value)
            transaction = None
            statements.append(statement)
        elif statement is None:
            continue
        elif tag == '25':
            statement['account_number'], currency = _account(value)
            statement['currency_code'] = statement['currency_code'] or currency
        elif tag in ('28', '28C'):
            statement['name'] = value.strip() or statement['name']
        elif tag in ('60F', '60M'):
            balance = _balance(value)
            if balance and statement['balance_start'] is None:
                statement['balance_start'] = balance[0]
                statement['currency_code'] = statement['currency_code'] or balance[1]
        elif tag in ('62F', '62M'):
            balance = _balance(value)
            if balance:
                statement['balance_end_real'] = balance[0]
                statement['currency_code'] = statement['currency_code'] or balance[1]
                statement['date'] = balance[2]
            transaction = None
        elif tag == '61':
            transaction = _transaction(value, statement, len(statement['transactions']))
            if transaction:
                statement['transactions'].append(transaction)
        elif tag == '86' and transaction is not None:
            _information(transaction, value)
            transaction = None
    for statement in statements:
        if not statement['date'] and statement['transactions']:
            statement['date'] = max(line['date'] for line in statement['transactions'])
    return statements


def _new_statement(reference):
    return {
        'name': reference.strip() or None,
        'date': None,
        'balance_start': None,
        'balance_end_real': None,
        'currency_code': None,
        'account_number': None,
        'transactions': [],
    }


def _transaction(value, statement, index):
    match = LINE.match(value.strip())
    if not match:
        return None
    value_date = _date(match.group('value_date'))
    entry_date = _entry_date(match.group('entry_date'), value_date)
    amount = _number(match.group('amount'))
    # RC and RD are reversals, they cancel a credit and a debit.
    mark = match.group('mark')
    if mark in ('D', 'RC'):
        amount = -amount
    references, dummy, extra = match.group('references').partition('\n')
    customer_reference, dummy, bank_reference = references.strip().partition('//')
    customer_reference = customer_reference.strip()
    bank_reference = bank_reference.strip()
    if customer_reference.upper() in EMPTY_REFERENCES:
        customer_reference = ''
    # Two transactions of a day can carry the same amount and the same reference, the number of the
    # statement and the position of the line keep their identifiers apart.
    parts = [bank_reference or customer_reference, statement['name'], str(index + 1)]
    return {
        'date': entry_date or value_date,
        'payment_ref': customer_reference or bank_reference or '/',
        'amount': amount,
        'unique_import_id': '-'.join(part for part in parts if part),
        'partner_name': None,
        'account_number': None,
        'ref': customer_reference or bank_reference or None,
        'narration': extra.strip() or None,
        'transaction_type': (match.group('transaction_type') or '').strip() or None,
    }


def _information(transaction, value):
    """Read a :86: into the line above it, whichever shape the bank gave it."""
    value = value.strip()
    transaction['narration'] = value or transaction['narration']
    label = partner_name = account_number = None
    if SLASH_FIELD.search(value):
        fields = _slash_fields(value)
        partner_name = fields.get('NAME') or _party_name(fields)
        account_number = fields.get('IBAN') or fields.get('ACCT') or _party_account(fields)
        label = fields.get('REMI') or fields.get('RMTINF') or fields.get('EREF')
        if label:
            label = label.replace('/', ' ').strip()
    elif SUBFIELD.search(value):
        fields = _subfields(value)
        partner_name = ' '.join(fields.get(key, '') for key in ('32', '33')).strip() or None
        account_number = fields.get('31')
        label = ' '.join(fields.get(key, '') for key in DESCRIPTION_SUBFIELDS if fields.get(key)).strip()
        label = label or fields.get('00')
    else:
        label = ' '.join(value.split())
    transaction['payment_ref'] = label or partner_name or transaction['payment_ref']
    transaction['partner_name'] = partner_name or transaction['partner_name']
    transaction['account_number'] = account_number or transaction['account_number']
    transaction['ref'] = transaction['ref'] or label


def _slash_fields(value):
    """``/EREF/1234/NAME/John Doe/REMI/Invoice 42`` read as a dict, the unknown parts dropped."""
    fields = {}
    parts = SLASH_FIELD.split(value)
    for index in range(1, len(parts) - 1, 2):
        key, content = parts[index], parts[index + 1]
        content = content.strip().strip('/').strip()
        if content and key not in fields:
            fields[key] = ' '.join(content.split())
    return fields


def _party_name(fields):
    # /CNTP/ holds the account, the bank, the name and the city of the other party, in this order.
    counterparty = (fields.get('CNTP') or '').split('/')
    return counterparty[2].strip() if len(counterparty) > 2 and counterparty[2].strip() else None


def _party_account(fields):
    counterparty = (fields.get('CNTP') or '').split('/')
    return counterparty[0].strip() if counterparty and counterparty[0].strip() else None


def _subfields(value):
    fields = {}
    for key, content in SUBFIELD.findall(value):
        content = ' '.join(content.split())
        fields[key] = ('%s %s' % (fields[key], content)).strip() if key in fields else content
    return fields


# -------------------------------------------------------------------------
# Format helpers
# -------------------------------------------------------------------------

def _tags(text):
    """The ``(tag, value)`` pairs of the file, the lines that carry no tag continuing the one above."""
    pairs = []
    for line in text.split('\n'):
        match = TAG.match(line.rstrip('\r'))
        if match:
            pairs.append([match.group(1), match.group(2)])
        elif pairs and line.strip() and line.strip() != '-':
            pairs[-1][1] += '\n' + line.rstrip('\r')
    return pairs


def _unwrap(text):
    """Drop the envelope of the files that come out of a SWIFT network: ``{1:..}{2:..}{4:`` .. ``-}``."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if '{4:' in text:
        body = text.split('{4:', 1)[1]
        text = body.rsplit('-}', 1)[0] if '-}' in body else body
    return text


def _account(value):
    """``:25:`` is the account, sometimes followed by the currency of the statement."""
    parts = value.strip().replace('/', ' ').split()
    currency = None
    if len(parts) > 1 and len(parts[-1]) == 3 and parts[-1].isalpha():
        currency = parts.pop().upper()
    # some banks put the BIC of their branch in front of the account
    if len(parts) == 2 and BIC.match(parts[0].upper()):
        parts = parts[1:]
    return (''.join(parts) or None), currency


def _balance(value):
    match = BALANCE.match(value.strip())
    if not match:
        return None
    amount = _number(match.group('amount'))
    if match.group('mark') == 'D':
        amount = -amount
    return amount, match.group('currency'), _date(match.group('date'))


def _number(text):
    text = text.strip()
    # the decimal separator is the comma, a dot can only be a thousands separator
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    return float(text.rstrip('.') or 0)


def _date(text):
    year, month, day = 2000 + int(text[:2]), int(text[2:4]), int(text[4:6])
    return date(year, month, day)


def _entry_date(text, value_date):
    """``:61:`` gives the entry date without its year, it is the one of the value date, or the one next
    to it when the statement runs over the end of a year."""
    if not text or not value_date:
        return None
    month, day = int(text[:2]), int(text[2:])
    for year in (value_date.year, value_date.year - 1, value_date.year + 1):
        try:
            entry_date = date(year, month, day)
        except ValueError:
            continue
        if abs(entry_date - value_date) <= timedelta(days=300):
            return entry_date
    return None


def _decode(data):
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass
    try:
        import chardet
        encoding = (chardet.detect(data) or {}).get('encoding')
        if encoding:
            return data.decode(encoding, errors='replace')
    except ImportError:
        pass
    return data.decode('latin-1')
