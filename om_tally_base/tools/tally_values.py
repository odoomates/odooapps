""" Values of Tally XML: numbers, amounts, quantities, dates and flags.

Tally writes the sign of an amount the opposite way of Odoo: a debit is negative, a credit positive, for ledger
opening balances, voucher lines, bill allocations and stock opening values alike. ISDEEMEDPOSITIVE says the same
(Yes: debit side). ``tally_debit`` is the only place that turns a Tally amount into the Odoo convention (debit
positive, credit negative): every other part of the connector calls it.
"""
import re
from datetime import date, datetime, timedelta

NUMBER = re.compile(r'\d[\d,]*(?:\.\d+)?|\.\d+')
DAYS = re.compile(r'(-?\d+)\s*(day|days|d)?\b', re.I)
DATE_FORMATS = ('%Y%m%d', '%d-%b-%Y', '%d-%b-%y', '%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d', '%d.%m.%Y', '%d %b %Y')

# The 28 groups every Tally company has: name -> (nature, parent)
PREDEFINED_GROUPS = {
    'Branch / Divisions': ('liability', False),
    'Capital Account': ('liability', False),
    'Current Assets': ('asset', False),
    'Current Liabilities': ('liability', False),
    'Direct Expenses': ('expense', False),
    'Direct Incomes': ('income', False),
    'Fixed Assets': ('asset', False),
    'Indirect Expenses': ('expense', False),
    'Indirect Incomes': ('income', False),
    'Investments': ('asset', False),
    'Loans (Liability)': ('liability', False),
    'Misc. Expenses (ASSET)': ('asset', False),
    'Purchase Accounts': ('expense', False),
    'Sales Accounts': ('income', False),
    'Suspense A/c': ('liability', False),
    'Bank Accounts': ('asset', 'Current Assets'),
    'Bank OD A/c': ('liability', 'Loans (Liability)'),
    'Cash-in-Hand': ('asset', 'Current Assets'),
    'Deposits (Asset)': ('asset', 'Current Assets'),
    'Duties & Taxes': ('liability', 'Current Liabilities'),
    'Loans & Advances (Asset)': ('asset', 'Current Assets'),
    'Provisions': ('liability', 'Current Liabilities'),
    'Reserves & Surplus': ('liability', 'Capital Account'),
    'Secured Loans': ('liability', 'Loans (Liability)'),
    'Stock-in-Hand': ('asset', 'Current Assets'),
    'Sundry Creditors': ('liability', 'Current Liabilities'),
    'Sundry Debtors': ('asset', 'Current Assets'),
    'Unsecured Loans': ('liability', 'Loans (Liability)'),
}

# The voucher types of Tally; custom types are based on one of them
PREDEFINED_VOUCHER_TYPES = [
    'Sales', 'Purchase', 'Receipt', 'Payment', 'Contra', 'Journal', 'Credit Note', 'Debit Note',
    'Reversing Journal', 'Memorandum', 'Sales Order', 'Purchase Order', 'Delivery Note', 'Receipt Note',
    'Rejections In', 'Rejections Out', 'Stock Journal', 'Physical Stock', 'Material In', 'Material Out',
    'Job Work In Order', 'Job Work Out Order', 'Payroll', 'Attendance',
]
# The types that post to the books: the others (orders, notes, stock journals, memos) do not
ACCOUNTING_VOUCHER_TYPES = {
    'Sales', 'Purchase', 'Receipt', 'Payment', 'Contra', 'Journal', 'Credit Note', 'Debit Note', 'Payroll',
}


def tally_bool(value):
    """ Tally flags are 'Yes' / 'No'. """
    return (value or '').strip().lower() in ('yes', 'true', '1')


def tally_number(value):
    """ The number in a Tally value, signed: '-1,180.00', ' 10 Nos', '-$100.00 @ Rs 82/$ = -Rs 8200.00' (the
    amount in the base currency, after the '=', wins). """
    if not value:
        return 0.0
    text = str(value)
    if '=' in text:
        text = text.rsplit('=', 1)[1]
    elif '@' in text:
        text = text.split('@', 1)[0]
    match = NUMBER.search(text)
    if not match:
        return 0.0
    number = float(match.group(0).replace(',', ''))
    if '-' in text[:match.start()] or text[:match.start()].strip().startswith('('):
        number = -number
    return number


def tally_debit(value):
    """ A Tally amount in the Odoo convention: the debit positive, the credit negative. """
    return -tally_number(value)


def tally_quantity(value):
    """ (quantity, unit) of a Tally quantity: ' 10 Nos', '-2.5 Kg', '12 Nos = 1 Box' (the first part wins). """
    if not value:
        return 0.0, ''
    text = str(value).split('=', 1)[0].strip()
    match = NUMBER.search(text)
    if not match:
        return 0.0, text
    quantity = float(match.group(0).replace(',', ''))
    if '-' in text[:match.start()]:
        quantity = -quantity
    return quantity, text[match.end():].strip()


def tally_rate(value):
    """ The rate of '100.00/Nos' or '$ 2.50/Nos = Rs 207.50/Nos'. """
    if not value:
        return 0.0
    text = str(value)
    if '=' in text:
        text = text.rsplit('=', 1)[1]
    return abs(tally_number(text.split('/', 1)[0]))


def tally_date(value):
    """ A date of Tally: '20250401' in XML, '1-Apr-2025' in some reports. """
    if not value:
        return False
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return False


def tally_due_date(bill_date, credit_period):
    """ The due date of a bill: its credit period is a number of days ('30 Days') or a date. """
    if not bill_date or not credit_period:
        return bill_date or False
    as_date = tally_date(credit_period)
    if as_date:
        return as_date
    match = DAYS.search(str(credit_period))
    if match:
        return bill_date + timedelta(days=int(match.group(1)))
    return bill_date
