"""Parsers of the bank statement files.

Each parser is a module with a ``parse(data, filename, options)`` function:

:param bytes data: the contents of the file
:param str filename: the name of the file, used to recognise a format by its extension
:param dict options: ``{'map': dict|None, 'date_format': str|None}``, the settings of the file map of the
    wizard, for the formats whose layout is not fixed
:return: the statements of the file, or ``None`` when the file is not of the format of the parser, so that
    the next parser is tried. A file of the right format but unreadable raises a ``ValueError`` instead.
:rtype: list[dict] | None

A statement is a dict::

    {
        'name': str | None,                 # the number or the name of the statement in the file
        'date': datetime.date | None,       # the closing date, the date of the last transaction by default
        'balance_start': float | None,
        'balance_end_real': float | None,
        'currency_code': str | None,        # ISO code, checked against the journal
        'account_number': str | None,       # the bank account of the statement, used to find the journal
        'transactions': [transaction],
    }

A transaction is a dict, where only ``date``, ``payment_ref`` and ``amount`` are required::

    {
        'date': datetime.date,
        'payment_ref': str,                 # the label of the line
        'amount': float,                    # negative when the money leaves the account
        'unique_import_id': str | None,     # the id of the transaction in the file, unique for the account
        'partner_name': str | None,
        'account_number': str | None,       # the bank account of the other party
        'ref': str | None,
        'narration': str | None,
        'transaction_type': str | None,
    }
"""

from . import camt
from . import csv_file
from . import mt940
from . import ofx
from . import qif
