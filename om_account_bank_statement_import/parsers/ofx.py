"""OFX and QFX, the format of most banks of the United States and of Canada."""

import io
import re

TRANSACTION = re.compile(r'<STMTTRN>(.*?)</STMTTRN>', re.IGNORECASE | re.DOTALL)
FITID = re.compile(r'<FITID>\s*([^<\r\n]*)', re.IGNORECASE)
# <CURRENCY>: the amounts of the transaction are in CURSYM; <ORIGCURRENCY>: they were converted from CURSYM.
CURRENCY = re.compile(r'<(CURRENCY|ORIGCURRENCY)>(.*?)</\1>', re.IGNORECASE | re.DOTALL)
CURRATE = re.compile(r'<CURRATE>\s*([^<\r\n]*)', re.IGNORECASE)
CURSYM = re.compile(r'<CURSYM>\s*([^<\r\n]*)', re.IGNORECASE)


def parse(data, filename, options=None):
    header = data[:1024].upper()
    if b'<OFX>' not in header and b'OFXHEADER' not in header:
        return None
    try:
        from ofxparse import OfxParser  # noqa: PLC0415
    except ImportError:
        raise ValueError("The Python library 'ofxparse' is needed to import an OFX file.") from None
    try:
        ofx = OfxParser.parse(io.BytesIO(data))
    except Exception as error:
        raise ValueError(f"This OFX file cannot be read: {error}") from error

    currencies = _transaction_currencies(data)
    statements = []
    for account in ofx.accounts:
        statement = account.statement
        account_currency = (getattr(statement, 'currency', None) or '').upper()
        transactions = []
        for index, transaction in enumerate(statement.transactions):
            label = (transaction.payee or transaction.memo or '').strip()
            memo = (transaction.memo or '').strip()
            amount = float(transaction.amount)
            amount_currency = foreign_currency_code = None
            currency = currencies.get((transaction.id or '').strip())
            # a currency of the transaction that is the one of the account changes nothing
            if currency and currency[2] != account_currency:
                kind, rate, foreign_currency_code = currency
                if kind == 'CURRENCY':
                    # the amount of the file is the foreign one, the rate gives the one of the account
                    amount_currency, amount = amount, amount * rate
                else:
                    amount_currency = amount / rate
            transactions.append({
                'date': transaction.date.date(),
                'payment_ref': label or memo or f'{transaction.type} {transaction.amount}',
                'amount': amount,
                # the id of a transaction is unique for the account it belongs to
                'unique_import_id': (transaction.id or '').strip() or f'{account.number}-{index}',
                'ref': (transaction.checknum or '').strip() or None,
                'narration': memo if memo and memo != label else None,
                'transaction_type': transaction.type or None,
                'amount_currency': amount_currency,
                'foreign_currency_code': foreign_currency_code,
            })
        statements.append({
            'name': None,
            'date': statement.end_date.date() if statement.end_date else None,
            'balance_start': None,
            'balance_end_real': float(statement.balance) if statement.balance is not None else None,
            'currency_code': getattr(statement, 'currency', None) or None,
            'account_number': account.number or None,
            'transactions': transactions,
        })
    if not statements:
        raise ValueError("This OFX file holds no account.")
    return statements


def _transaction_currencies(data):
    """ :return: {FITID: (CURRENCY or ORIGCURRENCY, CURRATE, CURSYM)} of the transactions of the file that
    carry a currency of their own, which ofxparse does not read. CURRATE is the ratio of the currency of the
    account (CURDEF) to CURSYM: an amount in CURSYM times CURRATE is the amount in CURDEF. """
    text = data.decode('latin-1')
    currencies = {}
    for block in TRANSACTION.findall(text):
        fitid = FITID.search(block)
        currency = CURRENCY.search(block)
        if not fitid or not fitid.group(1).strip() or not currency:
            continue
        rate = CURRATE.search(currency.group(2))
        code = CURSYM.search(currency.group(2))
        try:
            rate = float(rate.group(1).strip().replace(',', '.')) if rate else 0.0
        except ValueError:
            rate = 0.0
        code = code.group(1).strip().upper() if code else ''
        if rate <= 0 or len(code) != 3:
            continue
        fitid = fitid.group(1).strip()
        value = (currency.group(1).upper(), rate, code)
        # an identifier is unique for its account only: two accounts of the file sharing one are left alone
        currencies[fitid] = value if currencies.get(fitid, value) == value else None
    return currencies
