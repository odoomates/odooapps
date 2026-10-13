"""CAMT files, the ISO 20022 XML statements: camt.053, and the camt.052 reports and camt.054 notifications.

The namespaces are ignored, the tags are matched on their local name only, because the banks send every
version of the schema and some of them send no namespace at all.
"""

import re
from datetime import datetime

from lxml import etree

# The three root elements of the format, with the element of a statement in each of them.
DOCUMENTS = {
    'BkToCstmrStmt': 'Stmt',
    'BkToCstmrAcctRpt': 'Rpt',
    'BkToCstmrDbtCdtNtfctn': 'Ntfctn',
}

# The codes of the balances, the booked ones first and the available ones as a fallback.
OPENING_CODES = ('OPBD', 'PRCD')
CLOSING_CODES = ('CLBD',)
OPENING_FALLBACK_CODES = ('OPAV',)
CLOSING_FALLBACK_CODES = ('CLAV',)

# The identifiers the banks send when there is none.
EMPTY_REFERENCES = ('NOTPROVIDED', 'NOTPROVIDE', 'UNKNOWN', 'NONREF')


def parse(data, filename, options=None):
    root = _root(data)
    if root is None:
        return None
    documents = [node for node in root.iter() if _local(node) in DOCUMENTS]
    if not documents:
        return None
    statements = []
    for document in documents:
        for node in _findall(document, DOCUMENTS[_local(document)]):
            statements.append(_statement(node, document))
    return statements


# -------------------------------------------------------------------------
# Statements
# -------------------------------------------------------------------------

def _statement(node, document):
    account = _find(node, 'Acct')
    balance_start, balance_end, balance_date = _balances(node)
    transactions = []
    currency = _text(account, 'Ccy')
    for index, entry in enumerate(_findall(node, 'Ntry')):
        transactions += _transactions(entry, index)
        currency = currency or _amount(entry)[1]
    date = balance_date or _date(node, 'CreDtTm') or _date(document, 'GrpHdr/CreDtTm')
    dates = [transaction['date'] for transaction in transactions if transaction['date']]
    if not date and dates:
        date = max(dates)
    return {
        'name': _text(node, 'Id', 'ElctrncSeqNb', 'LglSeqNb'),
        'date': date,
        'balance_start': balance_start,
        'balance_end_real': balance_end,
        'currency_code': currency,
        'account_number': _text(account, 'Id/IBAN', 'Id/Othr/Id'),
        'transactions': transactions,
    }


def _balances(node):
    """The opening and the closing balance of a statement, with the date of the closing one."""
    balances = {}
    date = None
    for balance in _findall(node, 'Bal'):
        code = _text(balance, 'Tp/CdOrPrtry/Cd', 'Tp/CdOrPrtry/Prtry')
        amount = _sign(_amount(balance)[0], _text(balance, 'CdtDbtInd'))
        if amount is None or not code:
            continue
        balances.setdefault(code, amount)
        if code in CLOSING_CODES:
            date = date or _date(balance, 'Dt/Dt', 'Dt/DtTm')
    def pick(codes):
        return next((balances[code] for code in codes if code in balances), None)
    balance_start = pick(OPENING_CODES)
    balance_end = pick(CLOSING_CODES)
    if balance_start is None:
        balance_start = pick(OPENING_FALLBACK_CODES)
    if balance_end is None:
        balance_end = pick(CLOSING_FALLBACK_CODES)
        date = date or next((_date(balance, 'Dt/Dt', 'Dt/DtTm') for balance in _findall(node, 'Bal')
                             if _text(balance, 'Tp/CdOrPrtry/Cd') in CLOSING_FALLBACK_CODES), None)
    return balance_start, balance_end, date


# -------------------------------------------------------------------------
# Transactions
# -------------------------------------------------------------------------

def _transactions(entry, index):
    """The transactions of an Ntry element, several of them when the entry is a batch."""
    amount, dummy = _amount(entry)
    indicator = _text(entry, 'CdtDbtInd')
    # A reversal keeps the indicator of the transaction it cancels, its amount goes the other way.
    reversal = (_text(entry, 'RvslInd') or '').lower() in ('true', '1')
    entry_reference = _text(entry, 'AcctSvcrRef', 'NtryRef')
    values = {
        'date': (_date(entry, 'BookgDt/Dt', 'BookgDt/DtTm')
                 or _date(entry, 'ValDt/Dt', 'ValDt/DtTm')),
        'amount': _sign(amount, indicator, reversal),
        'narration': _text(entry, 'AddtlNtryInf'),
        'transaction_type': _text(entry, 'BkTxCd/Prtry/Cd', 'BkTxCd/Domn/Fmly/SubFmlyCd', 'BkTxCd/Domn/Cd'),
        'partner_name': None,
        'account_number': None,
        'ref': None,
    }
    details = [transaction for group in _findall(entry, 'NtryDtls')
               for transaction in _children(group, 'TxDtls')]
    # A batch is split in one transaction per TxDtls, but only when each of them carries its own amount.
    batch = len(details) > 1 and all(_find(transaction, 'Amt') is not None for transaction in details)
    if not batch:
        details = details[:1]
    transactions = []
    for sub_index, detail in enumerate(details or [None]):
        transaction = dict(values)
        if detail is not None:
            transaction.update(_details(detail, indicator, reversal, batch))
        # the reference of the entry identifies it, the one of the detail only tells a batch apart
        detail_reference = transaction.pop('reference', None)
        reference = (detail_reference if batch else None) or entry_reference
        if batch and reference == entry_reference:
            reference = '%s-%s' % (entry_reference or 'entry%s' % (index + 1), sub_index + 1)
        transaction['unique_import_id'] = reference
        transaction['payment_ref'] = (transaction['ref'] or transaction['narration']
                                      or transaction['partner_name'] or reference or '/')
        transactions.append(transaction)
    return transactions


def _details(node, indicator, reversal, batch):
    """The values of a TxDtls element, ``indicator`` being the direction of its entry."""
    values = {}
    amount, dummy = _amount(node)
    if amount is not None and batch:
        values['amount'] = _sign(amount, _text(node, 'CdtDbtInd') or indicator, reversal)
    parties = _find(node, 'RltdPties')
    if parties is not None:
        # The other party is the creditor of a payment and the debtor of a collection.
        party, party_account = ('Cdtr', 'CdtrAcct') if indicator == 'DBIT' else ('Dbtr', 'DbtrAcct')
        values['partner_name'] = _text(parties, party + '/Nm', party + '/Pty/Nm')
        values['account_number'] = _text(parties, party_account + '/Id/IBAN', party_account + '/Id/Othr/Id')
    unstructured = [(found.text or '').strip() for found in _findall(node, 'RmtInf/Ustrd')]
    values['ref'] = (' '.join(text for text in unstructured if text)
                     or _text(node, 'RmtInf/Strd/CdtrRefInf/Ref')
                     or _reference(node, 'Refs/EndToEndId')
                     or _reference(node, 'Refs/InstrId'))
    values['reference'] = _reference(node, 'Refs/AcctSvcrRef') or _reference(node, 'Refs/EndToEndId')
    narration = _text(node, 'AddtlTxInf')
    if narration:
        values['narration'] = narration
    return values


def _reference(node, path):
    reference = _text(node, path)
    return reference if reference and reference.upper() not in EMPTY_REFERENCES else None


# -------------------------------------------------------------------------
# XML helpers
# -------------------------------------------------------------------------

def _root(data):
    if isinstance(data, str):
        data = data.encode()
    if not data.lstrip(b'\xef\xbb\xbf \t\r\n').startswith(b'<'):
        return None
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True)
    try:
        return etree.fromstring(data, parser=parser)
    except etree.XMLSyntaxError:
        pass
    # The contents of the file do not match the encoding of its declaration, drop the declaration.
    try:
        text = re.sub(r'^\s*<\?xml[^>]*\?>', '', _decode(data))
        return etree.fromstring(text, parser=parser)
    except (etree.XMLSyntaxError, ValueError):
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


def _local(node):
    tag = node.tag
    return tag.rpartition('}')[2] if isinstance(tag, str) else ''


def _children(node, tag):
    return [child for child in node if _local(child) == tag]


def _findall(node, path):
    nodes = [node] if node is not None else []
    for tag in path.split('/'):
        nodes = [child for parent in nodes for child in _children(parent, tag)]
    return nodes


def _find(node, path):
    return next(iter(_findall(node, path)), None)


def _text(node, *paths):
    for path in paths:
        for found in _findall(node, path):
            text = (found.text or '').strip()
            if text:
                return text
    return None


def _date(node, *paths):
    text = _text(node, *paths)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _amount(node, path='Amt'):
    found = _find(node, path)
    if found is None:
        return None, None
    text = (found.text or '').strip()
    try:
        # the schema has a dot, a few banks send a comma anyway
        return float(text.replace(',', '.')), found.get('Ccy')
    except ValueError:
        return None, found.get('Ccy')


def _sign(amount, indicator, reversal=False):
    if amount is None:
        return None
    negative = indicator == 'DBIT'
    if reversal:
        negative = not negative
    return -abs(amount) if negative else abs(amount)
