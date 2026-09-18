"""OFX and QFX, the format of most banks of the United States and of Canada."""

import io


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

    statements = []
    for account in ofx.accounts:
        statement = account.statement
        transactions = []
        for index, transaction in enumerate(statement.transactions):
            label = (transaction.payee or transaction.memo or '').strip()
            memo = (transaction.memo or '').strip()
            transactions.append({
                'date': transaction.date.date(),
                'payment_ref': label or memo or f'{transaction.type} {transaction.amount}',
                'amount': float(transaction.amount),
                # the id of a transaction is unique for the account it belongs to
                'unique_import_id': (transaction.id or '').strip() or f'{account.number}-{index}',
                'ref': (transaction.checknum or '').strip() or None,
                'narration': memo if memo and memo != label else None,
                'transaction_type': transaction.type or None,
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
