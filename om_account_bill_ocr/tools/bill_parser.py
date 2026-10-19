""" Reading the fields of a vendor bill from its text.

Plain Python, no Odoo: the text in, a dict of what was found out. Each value is found from the labels printed
next to it (Invoice No, Due Date, Total...) in English, French, German and Spanish, and the amounts are checked
against each other: the lines are only kept when they add up to the untaxed amount, and the untaxed amount and
the taxes when they add up to the total. What a vendor's bill taught is given back as `anchors`, the label
printed before each field on that vendor's bills, and read first. """
import re
from datetime import date

# ------------------------------------------------------------------------------------------------------------
# numbers
# ------------------------------------------------------------------------------------------------------------

# 1,234.56  1.234,56  1 234,56  1'234.56  1234.56  -12.00  (12.00)
AMOUNT_RE = re.compile(r"""
    (?<![\w.,/:-])
    (?P<neg>[-(])?
    (?P<num>\d{1,3}(?:[ ,.'  ]\d{3})+(?:[.,]\d{1,3})?|\d+(?:[.,]\d{1,3})?)
    (?P<close>\))?
    (?![\w/:]|[.,]\d)
    (?!\s?%)
""", re.VERBOSE)
PERCENT_RE = re.compile(r'\d+(?:[.,]\d+)?\s?%')


def parse_amount(token, decimals=2):
    """ The value of a printed amount, whatever its separators. """
    token = token.strip().replace(' ', ' ').replace(' ', ' ')
    negative = token.startswith(('-', '(')) or token.endswith(')')
    token = token.strip('-() ')
    last_sep = max(token.rfind('.'), token.rfind(','))
    if last_sep == -1:
        integer, fraction = token, ''
    else:
        digits_after = len(token) - last_sep - 1
        separators = set(re.findall(r'[ ,.\']', token))
        single_sep = len(separators) == 1 and token.count(token[last_sep]) == 1
        if digits_after == 3 and single_sep and decimals != 3:
            # 1,234 or 1.234: a thousands separator, unless the currency has 3 decimals
            integer, fraction = token, ''
        elif digits_after <= (3 if decimals == 3 else 2):
            integer, fraction = token[:last_sep], token[last_sep + 1:]
        else:
            integer, fraction = token, ''
    integer = re.sub(r'\D', '', integer)
    if not integer and not fraction:
        return None
    value = float(f"{integer or '0'}.{fraction or '0'}")
    return -value if negative else value


def find_amounts(text, decimals=2):
    """ The amounts of a piece of text, in order, with their position. """
    found = []
    for match in AMOUNT_RE.finditer(text):
        value = parse_amount(match.group(0), decimals)
        if value is not None:
            found.append((value, match.start(), match.end()))
    return found


def close(a, b, tolerance=0.011):
    return a is not None and b is not None and abs(a - b) <= max(tolerance, abs(b) * 0.0005)


# ------------------------------------------------------------------------------------------------------------
# dates
# ------------------------------------------------------------------------------------------------------------

MONTHS = {
    'jan': 1, 'janv': 1, 'january': 1, 'janvier': 1, 'januar': 1, 'enero': 1, 'ene': 1,
    'feb': 2, 'fev': 2, 'fév': 2, 'february': 2, 'février': 2, 'fevrier': 2, 'februar': 2, 'febrero': 2,
    'mar': 3, 'mars': 3, 'march': 3, 'märz': 3, 'marz': 3, 'marzo': 3,
    'apr': 4, 'avr': 4, 'april': 4, 'avril': 4, 'abril': 4, 'abr': 4,
    'may': 5, 'mai': 5, 'mayo': 5,
    'jun': 6, 'june': 6, 'juin': 6, 'juni': 6, 'junio': 6,
    'jul': 7, 'july': 7, 'juillet': 7, 'juil': 7, 'juli': 7, 'julio': 7,
    'aug': 8, 'august': 8, 'août': 8, 'aout': 8, 'agosto': 8, 'ago': 8,
    'sep': 9, 'sept': 9, 'september': 9, 'septembre': 9, 'septiembre': 9,
    'oct': 10, 'october': 10, 'octobre': 10, 'okt': 10, 'oktober': 10, 'octubre': 10,
    'nov': 11, 'november': 11, 'novembre': 11, 'noviembre': 11,
    'dec': 12, 'déc': 12, 'december': 12, 'décembre': 12, 'decembre': 12, 'dez': 12, 'dezember': 12,
    'dic': 12, 'diciembre': 12,
}
MONTH_NAMES = '|'.join(sorted(MONTHS, key=len, reverse=True))
DATE_RES = [
    # 2026-03-12
    ('ymd', re.compile(r'(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)')),
    # 12/03/2026, 03/12/26
    ('num', re.compile(r'(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})(?![\d/.-]\d)')),
    # 12 March 2026, 12-Mar-2026, 12. März 2026
    ('dmy_text', re.compile(rf'(?<!\w)(\d{{1,2}})(?:st|nd|rd|th|er)?\.?[\s\-/]*({MONTH_NAMES})\.?[\s\-/,]*(\d{{4}}|\d{{2}})(?!\d)',
                            re.IGNORECASE)),
    # March 12, 2026
    ('mdy_text', re.compile(rf'(?<!\w)({MONTH_NAMES})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})(?!\d)', re.IGNORECASE)),
]


def _year(value):
    year = int(value)
    return year + 2000 if year < 100 else year


def _make_date(year, month, day):
    try:
        found = date(year, month, day)
    except ValueError:
        return None
    return found if 1990 <= found.year <= 2100 else None


def find_dates(text, date_order='dmy'):
    """ The dates of a piece of text, in order: (date, start, kind). `kind` is the printed order of a numeric
    date, 'dmy' or 'mdy', None when the text leaves no doubt (a month in letters, a day over 12...). """
    found = []
    taken = []
    for name, regex in DATE_RES:
        for match in regex.finditer(text):
            if any(start <= match.start() < end for start, end in taken):
                continue
            kind = None
            if name == 'ymd':
                value = _make_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            elif name == 'num':
                first, second, year = int(match.group(1)), int(match.group(2)), _year(match.group(3))
                if '.' in match.group(0):
                    # 05.02.2026: the dotted dates are written day first, in every country printing them
                    value = _make_date(year, second, first)
                elif first > 12 and second <= 12:
                    value = _make_date(year, second, first)
                elif second > 12 and first <= 12:
                    value = _make_date(year, first, second)
                else:
                    kind = date_order
                    value = _make_date(year, second, first) if date_order == 'dmy' else _make_date(year, first, second)
            elif name == 'dmy_text':
                value = _make_date(_year(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1)))
            else:
                value = _make_date(_year(match.group(3)), MONTHS[match.group(1).lower()], int(match.group(2)))
            if value:
                found.append((value, match.start(), kind))
                taken.append((match.start(), match.end()))
    return sorted(found, key=lambda item: item[1])


# ------------------------------------------------------------------------------------------------------------
# labels
# ------------------------------------------------------------------------------------------------------------

NUMBER_LABELS = [
    r'tax\s+invoice\s*(?:no|number|num|#)', r'invoice\s*(?:no|number|num|nbr|nr|ref(?:erence)?|id)\b\.?',
    r'invoice\s*#', r'inv\.?\s*(?:no|#|number)', r'bill\s*(?:no|number|#)', r'document\s*(?:no|number|#)',
    r'receipt\s*(?:no|number|#)', r'credit\s*note\s*(?:no|number|#)', r'facture\s*(?:n°|no|num[ée]ro|#)',
    r'n°\s*(?:de\s*)?facture', r'rechnungs?\s*-?\s*(?:nummer|nr|no)', r'factura\s*(?:n[°ºo]|n[úu]mero|#)',
    r'n[°º]\s*(?:de\s*)?factura', r'invoice\s*:', r'(?<![\w])invoice\s+(?=[A-Z]{0,4}[-/]?\d)',
]
DATE_LABELS = [
    r'invoice\s*date', r'date\s*of\s*(?:issue|invoice)', r'issue\s*date', r'issued\s*(?:on)?', r'bill\s*date',
    r'tax\s*point', r'date\s*de\s*(?:la\s*)?facture', r'date\s*d.?[ée]mission', r'rechnungsdatum',
    r'fecha\s*(?:de\s*)?(?:factura|emisi[óo]n)', r'(?<!due\s)(?<!due)\bdate\b', r'datum', r'fecha',
]
DUE_LABELS = [
    r'due\s*date', r'payment\s*due', r'due\s*(?:by|on)', r'pay(?:able)?\s*by', r'date\s*d.?[ée]ch[ée]ance',
    r'[ée]ch[ée]ance', r'f[äa]llig(?:keitsdatum|\s*am)?', r'zahlbar\s*bis', r'fecha\s*de\s*vencimiento',
    r'vencimiento',
]
TOTAL_LABELS = [
    r'grand\s*total', r'total\s*(?:amount\s*)?due', r'amount\s*due', r'balance\s*due', r'amount\s*payable',
    r'total\s*payable', r'invoice\s*total', r'total\s*(?:amount|invoice)', r'total\s*(?:incl|inc|including)',
    r'total\s*\(?(?:ttc|inkl|con\s*iva)', r'net\s*(?:amount\s*)?payable', r'montant\s*ttc', r'total\s*ttc',
    r'gesamt(?:betrag|summe)?', r'rechnungsbetrag', r'zu\s*zahlen', r'importe\s*total', r'total\s*a\s*pagar',
    r'\btotal\b',
]
UNTAXED_LABELS = [
    r'sub\s*-?\s*total', r'net\s*(?:amount|total|value)', r'total\s*(?:excl|excluding|ex|before|w/o|without)',
    r'untaxed', r'taxable\s*(?:amount|value)', r'amount\s*before\s*tax', r'total\s*h\.?t', r'montant\s*h\.?t',
    r'nettobetrag', r'netto(?:summe)?', r'zwischensumme', r'base\s*imponible', r'subtotal',
]
TAX_LABELS = [
    r'\bvat\b', r'\bgst\b', r'\bigst\b', r'\bcgst\b', r'\bsgst\b', r'\butgst\b', r'\bhst\b', r'\bpst\b',
    r'sales\s*tax', r'\btax\b', r'\btaxes\b', r'\btva\b', r'\bmwst\b', r'mehrwertsteuer', r'\bust\b',
    r'umsatzsteuer', r'\biva\b', r'\bimpuesto', r'\bvalue\s*added\s*tax',
]
EXCLUDE_TAX_LINE = re.compile(
    r'(?:vat|tax|gst|tva|trn)\s*(?:reg|registration|id|no|number|#|identification)|gstin|tax\s*invoice|'
    r'incl(?:uding|\.)?\s*(?:vat|tax|gst)|excl(?:uding|\.)?\s*(?:vat|tax|gst)|before\s*tax|ht\b|ttc\b|'
    r'subtotal|sub\s*total|total',
    re.IGNORECASE)
PO_LABELS = [
    r'p\.?\s*o\.?\s*(?:no|number|#|ref)?\b', r'purchase\s*order\s*(?:no|number|#)?', r'order\s*(?:no|number|#|ref)',
    r'your\s*(?:order|ref(?:erence)?)', r'bon\s*de\s*commande', r'bestell(?:nummer|nr)', r'pedido',
]
VAT_LABELS = (
    r'(?:vat|tva|btw|iva|mwst|ust|gst|tax|trn)\s*(?:reg(?:istration|\.)?\s*)?(?:id(?:entification)?|no|number|nr|#|n°)?'
    r'|tax\s*registration|trn|gstin|ust\s*-?\s*id(?:nr)?|steuer\s*-?\s*nr|n\.?\s*i\.?\s*f|c\.?\s*i\.?\s*f|'
    r'p\.?\s*iva|siret|siren|abn|ein|tin'
)


def _compile(labels):
    return [re.compile(label, re.IGNORECASE) for label in labels]


NUMBER_LABEL_RES = _compile(NUMBER_LABELS)
DATE_LABEL_RES = _compile(DATE_LABELS)
DUE_LABEL_RES = _compile(DUE_LABELS)
TOTAL_LABEL_RES = _compile(TOTAL_LABELS)
UNTAXED_LABEL_RES = _compile(UNTAXED_LABELS)
TAX_LABEL_RES = _compile(TAX_LABELS)
PO_LABEL_RES = _compile(PO_LABELS)
VAT_LABEL_RE = re.compile(rf'(?<![a-z])(?:{VAT_LABELS})(?![a-z])\s*[:.#]?\s*', re.IGNORECASE)

# an invoice number: letters, digits and separators, with a digit, not a date nor an amount
REFERENCE_RE = re.compile(r'(?<![\w/-])(?=[A-Z0-9/_.#-]*\d)([A-Z0-9][A-Z0-9/_.#-]{0,30}[A-Z0-9])(?![\w-])|(?<![\w])(\d)(?![\w])',
                          re.IGNORECASE)
NOT_A_REFERENCE = re.compile(r'^(?:no|nr|number|date|invoice|page|of|n°)$', re.IGNORECASE)


def _lines(text):
    return [line.rstrip() for line in text.replace('\f', '\n').split('\n')]


def _after_label(lines, label_res, value_finder, max_next=2, skip=None):
    """ The first value printed after one of the labels: on the same line, else on the next lines, under the
    label. Returns (value, label text, line index). """
    for label_re in label_res:
        for index, line in enumerate(lines):
            if skip and skip(line):
                continue
            for match in label_re.finditer(line):
                rest = line[match.end():]
                value = value_finder(rest)
                if value is not None:
                    return value, match.group(0), index
                # the value printed under the label, in the same column
                for offset in range(1, max_next + 1):
                    if index + offset >= len(lines):
                        break
                    below = lines[index + offset]
                    column = below[max(0, match.start() - 4):]
                    value = value_finder(column)
                    if value is not None:
                        return value, match.group(0), index
                    if below.strip():
                        break
    return None, None, None


# ------------------------------------------------------------------------------------------------------------
# parties
# ------------------------------------------------------------------------------------------------------------

IBAN_RE = re.compile(r'\b([A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?)\b')
EMAIL_RE = re.compile(r'[\w.+-]+@([\w-]+(?:\.[\w-]+)+)')
GSTIN_RE = re.compile(r'\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b')
EU_VAT_RE = re.compile(r'\b(?:AT|BE|BG|CY|CZ|DE|DK|EE|EL|ES|FI|FR|GB|HR|HU|IE|IT|LT|LU|LV|MT|NL|PL|PT|RO|SE|SI|SK|XI|CH|NO)'
                       r'\s?[0-9A-Z][0-9A-Z .]{6,13}[0-9A-Z]\b')
VAT_VALUE_RE = re.compile(r'([A-Z]{0,3}[\s-]?[0-9][0-9A-Z .\-/]{4,22}[0-9A-Z])', re.IGNORECASE)


def normalize_vat(value):
    return re.sub(r'[^0-9A-Z]', '', (value or '').upper())


def iban_is_valid(iban):
    iban = normalize_vat(iban)
    if not 15 <= len(iban) <= 34:
        return False
    moved = iban[4:] + iban[:4]
    digits = ''.join(str(int(char, 36)) for char in moved)
    return int(digits) % 97 == 1


def find_ibans(text):
    return list(dict.fromkeys(normalize_vat(match) for match in IBAN_RE.findall(text) if iban_is_valid(match)))


def find_vat_numbers(text):
    """ The tax identification numbers printed on the bill: after a label (VAT No, TRN, GSTIN, USt-IdNr...),
    or in the shape of a European VAT number or an Indian GSTIN. """
    found = []
    ibans = set(find_ibans(text))
    for line in _lines(text):
        for match in VAT_LABEL_RE.finditer(line):
            value = VAT_VALUE_RE.match(line[match.end():])
            if value:
                vat = normalize_vat(value.group(1))
                if sum(char.isdigit() for char in vat) >= 5:
                    found.append(vat)
    found += [normalize_vat(match) for match in GSTIN_RE.findall(text)]
    found += [normalize_vat(match) for match in EU_VAT_RE.findall(text)]
    return [vat for vat in dict.fromkeys(found) if vat not in ibans and not any(vat in iban for iban in ibans)]


def find_emails(text):
    return list(dict.fromkeys(match.group(0).lower() for match in EMAIL_RE.finditer(text)))


def header_lines(text, count=12):
    """ The first lines of text of the bill, where the vendor prints its name. """
    lines = []
    for line in _lines(text):
        for part in re.split(r'\s{3,}', line.strip()):
            part = part.strip(' :|-')
            if len(part) >= 3 and re.search(r'[A-Za-z]{3}', part):
                lines.append(part)
        if len(lines) >= count:
            break
    return lines[:count]


# ------------------------------------------------------------------------------------------------------------
# the fields
# ------------------------------------------------------------------------------------------------------------

def _reference_finder(rest):
    rest = re.sub(r'^[\s:#.\-n°º]*', '', rest, flags=re.IGNORECASE)
    for match in REFERENCE_RE.finditer(rest[:60]):
        value = match.group(1) or match.group(2)
        if NOT_A_REFERENCE.match(value) or find_dates(value):
            continue
        return value.strip('#.')
    return None


def _first_date_finder(date_order):
    def finder(rest):
        dates = find_dates(rest[:40], date_order)
        return dates[0][0] if dates else None
    return finder


def _labeled_amounts(lines, label_res, decimals, skip=None):
    """ Every amount printed after one of the labels: the rightmost amount of the line, the column of the
    total, else the amount printed under the label. """
    found = []
    for index, line in enumerate(lines):
        if skip and skip(line):
            continue
        for label_re in label_res:
            match = label_re.search(line)
            if not match:
                continue
            amounts = [amount for amount in find_amounts(line[match.end():], decimals)]
            if amounts:
                found.append((amounts[-1][0], index, match.group(0)))
            elif index + 1 < len(lines):
                below = find_amounts(lines[index + 1][max(0, match.start() - 4):], decimals)
                if below:
                    found.append((below[0][0], index, match.group(0)))
            break
    return found


def _totals(lines, decimals):
    """ The total, the untaxed amount and the taxes, checked against each other. """
    def is_tax_label_line(line):
        lowered = line.lower()
        return bool(EXCLUDE_TAX_LINE.search(lowered))

    def is_untaxed_line(line):
        return any(regex.search(line) for regex in UNTAXED_LABEL_RES)

    totals = _labeled_amounts(lines, TOTAL_LABEL_RES, decimals, skip=is_untaxed_line)
    untaxed = _labeled_amounts(lines, UNTAXED_LABEL_RES, decimals)
    taxes = _labeled_amounts(lines, TAX_LABEL_RES, decimals, skip=is_tax_label_line)
    total_values = [value for value, *_ in totals if value > 0]
    untaxed_values = [value for value, *_ in untaxed if value > 0]
    tax_values = [value for value, *_ in taxes if value >= 0]
    result = {'amount_total': None, 'amount_untaxed': None, 'amount_tax': None, 'totals_consistent': False}
    total = max(total_values) if total_values else None
    # the untaxed amount and the taxes that add up to the total: one tax, or several (CGST and SGST)
    for candidate_total in sorted(set(total_values), reverse=True):
        for net in sorted(set(untaxed_values), reverse=True):
            if net > candidate_total + 0.01:
                continue
            tax_sum = round(candidate_total - net, 2)
            if close(tax_sum, 0.0):
                result.update(amount_total=candidate_total, amount_untaxed=net, amount_tax=0.0, totals_consistent=True)
                return result
            unique_taxes = list(dict.fromkeys(tax_values))
            if any(close(value, tax_sum) for value in tax_values) or close(sum(tax_values), tax_sum) \
                    or close(sum(unique_taxes), tax_sum):
                result.update(amount_total=candidate_total, amount_untaxed=net, amount_tax=tax_sum,
                              totals_consistent=True)
                return result
        for value in tax_values:
            if 0 < value < candidate_total and not untaxed_values:
                result.update(amount_total=candidate_total, amount_untaxed=round(candidate_total - value, 2),
                              amount_tax=value)
    if result['amount_total'] is None:
        result['amount_total'] = total
        if untaxed_values and total and max(untaxed_values) <= total:
            result['amount_untaxed'] = max(v for v in untaxed_values if v <= total)
            result['amount_tax'] = round(total - result['amount_untaxed'], 2)
    return result


CURRENCY_SYMBOLS = {'€': 'EUR', '£': 'GBP', '₹': 'INR', '¥': 'JPY', '₩': 'KRW', '₺': 'TRY', '₽': 'RUB', '₦': 'NGN',
                    '₱': 'PHP', '฿': 'THB', '₫': 'VND', '₪': 'ILS', 'zł': 'PLN', 'R$': 'BRL', 'CHF': 'CHF',
                    'د.إ': 'AED', 'ر.س': 'SAR', 'د.ك': 'KWD', '$': 'USD'}
ISO_RE = re.compile(r'(?<![A-Z])([A-Z]{3})(?![A-Z])')


def find_currency(text, known_codes=()):
    """ The currency of the bill: an ISO code the database knows, else a currency symbol. """
    counts = {}
    for code in ISO_RE.findall(text):
        if code in known_codes:
            counts[code] = counts.get(code, 0) + 1
    if counts:
        return max(counts, key=counts.get)
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    return None


# ------------------------------------------------------------------------------------------------------------
# the lines
# ------------------------------------------------------------------------------------------------------------

HEADER_WORDS = {
    'description': r'description|item|product|particulars|service|details|designation|désignation|article|'
                   r'artikel|bezeichnung|leistung|concepto|descripci[óo]n|libell[ée]',
    'quantity': r'\bqty\b|quantity|qt[ée]|quantit[ée]|menge|anzahl|cantidad|\bunits?\b|\bhrs\b|hours|\bnos?\b',
    'price': r'unit\s*price|\bprice\b|\brate\b|unit\s*cost|prix|preis|einzelpreis|precio|\bp\.?u\b|tarif',
    'amount': r'amount|\btotal\b|line\s*total|montant|betrag|gesamt|importe|\bnet\b|value',
}
HEADER_RES = {key: re.compile(value, re.IGNORECASE) for key, value in HEADER_WORDS.items()}
END_OF_LINES_RE = re.compile('|'.join(UNTAXED_LABELS + TOTAL_LABELS[:-1]), re.IGNORECASE)
# a line starting with a tax or a total ends the table too: VAT 5%, Total AED
END_OF_LINES_START_RE = re.compile(r'^\s*(?:' + '|'.join(TAX_LABELS + [r'\btotal\b']) + ')', re.IGNORECASE)


def _find_header(lines):
    for index, line in enumerate(lines):
        hits = {key for key, regex in HEADER_RES.items() if regex.search(line)}
        if 'description' in hits and len(hits) >= 2 or len(hits) >= 3:
            return index
    return None


def _row_values(numbers, decimals):
    """ Quantity, unit price and amount from the numbers of a row: the amount is the last one, and the
    quantity and the price are the pair before it that multiply to it (a discount between them allowed). """
    values = [value for value, *_ in numbers]
    amount = values[-1]
    before = values[:-1]
    for i, quantity in enumerate(before):
        for price in before[i + 1:]:
            if close(quantity * price, amount, 0.02):
                return quantity, price, amount
            for discount in before:
                if 0 < discount < 100 and close(quantity * price * (1 - discount / 100), amount, 0.02):
                    return quantity, price * (1 - discount / 100), amount
    if len(before) == 1 and before[0] and close(before[0], amount):
        return 1.0, amount, amount
    if len(before) >= 1 and before[0] and float(before[0]).is_integer() and 0 < before[0] < 10000:
        return before[0], round(amount / before[0], decimals + 2), amount
    return 1.0, amount, amount


def _row_is_consistent(numbers):
    values = [value for value, *_ in numbers]
    if len(values) < 2:
        return False
    amount = values[-1]
    return any(close(q * p, amount, 0.02) for i, q in enumerate(values[:-1]) for p in values[i + 1:-1])


def _split_row(text, decimals):
    """ The description and the numbers of the right-hand columns of a row of the table. """
    numbers = find_amounts(text, decimals)
    # the numbers of the right-hand columns: the last ones, with only spaces or a currency between them
    columns = []
    for value, start, end in reversed(numbers):
        next_start = columns[0][1] if columns else len(text)
        if not re.fullmatch(r'[\s$€£₹¥]*(?:[A-Z]{3})?[\s$€£₹¥]*', text[end:next_start]):
            break
        columns.insert(0, (value, start, end))
    # a whole number glued to the description by a single space is part of it ("Widget 2000"), unless the
    # row only adds up with it as its quantity ("Toner, black 6.00  72.50  435.00" squeezed by the layout)
    while columns and re.search(r'\S \Z', text[:columns[0][1]]):
        glued = text[columns[0][1]:columns[0][2]]
        if _row_is_consistent(columns) and not _row_is_consistent(columns[1:]):
            break
        if re.search(r'[.,]\d{1,3}$', glued) and not _row_is_consistent(columns[1:]):
            break
        columns.pop(0)
    description_end = columns[0][1] if columns else len(text)
    description = re.sub(r'^\d{1,3}[.)]?\s+', '', text[:description_end].strip(' |:-'))
    return re.sub(r'\s{2,}', ' ', description).strip(), columns


def find_lines(lines, decimals=2):
    """ The lines of the bill, read from its table: the description on the left, the numbers on the right.
    A description may wrap: on the lines under its row, or around a row of numbers printed on a line of its
    own ("On-site printer" / numbers / "maintenance"). """
    header = _find_header(lines)
    if header is None:
        return []
    rows = []
    pending = []    # lines of text not yet given to a row
    blank = 0

    def flush_pending_to_last_row():
        if pending and rows:
            rows[-1]['name'] = ' '.join([rows[-1]['name'], *pending])
        pending.clear()

    for line in lines[header + 1:]:
        if END_OF_LINES_RE.search(line) or END_OF_LINES_START_RE.search(line):
            break
        if not line.strip():
            blank += 1
            if blank > 3 and rows:
                break
            continue
        blank = 0
        text = PERCENT_RE.sub(lambda m: ' ' * len(m.group(0)), line)
        description, numbers = _split_row(text, decimals)
        if numbers and re.search(r'[A-Za-z]', description):
            flush_pending_to_last_row()
            quantity, price, amount = _row_values(numbers, decimals)
            rows.append({'name': description, 'quantity': quantity, 'price_unit': price, 'amount': amount})
        elif numbers and not description and pending:
            # the numbers of a row whose description is printed above them
            quantity, price, amount = _row_values(numbers, decimals)
            rows.append({'name': ' '.join(pending), 'quantity': quantity, 'price_unit': price, 'amount': amount})
            pending.clear()
        elif not numbers and re.search(r'[A-Za-z]', line):
            # the rest of the description above, or the start of the next row: told by what follows
            if pending and rows:
                flush_pending_to_last_row()
            pending.append(re.sub(r'\s{2,}', ' ', line.strip()))
    flush_pending_to_last_row()
    return rows


# ------------------------------------------------------------------------------------------------------------
# the bill
# ------------------------------------------------------------------------------------------------------------

def _anchored(lines, anchor, finder):
    if not anchor:
        return None
    value, *_ = _after_label(lines, [re.compile(re.escape(anchor), re.IGNORECASE)], finder)
    return value


def parse_bill(text, date_order='dmy', decimals=2, anchors=None, known_currencies=()):
    """ Read a bill. `anchors` are the labels a vendor prints before its fields, learned from its earlier
    bills: {'ref': 'Invoice No.', 'invoice_date': 'Dated', 'amount_total': 'Total Payable'}. """
    anchors = anchors or {}
    lines = _lines(text)
    result = {'text_lines': len([line for line in lines if line.strip()])}

    reference = _anchored(lines, anchors.get('ref'), _reference_finder)
    reference_label = anchors.get('ref') if reference else None
    if not reference:
        reference, reference_label, _index = _after_label(lines, NUMBER_LABEL_RES, _reference_finder)
    result['ref'] = reference
    result['ref_label'] = reference_label

    date_finder = _first_date_finder(date_order)
    due = _anchored(lines, anchors.get('invoice_date_due'), date_finder)
    due_label = anchors.get('invoice_date_due') if due else None
    if not due:
        due, due_label, _index = _after_label(lines, DUE_LABEL_RES, date_finder)
    invoice_date = _anchored(lines, anchors.get('invoice_date'), date_finder)
    date_label = anchors.get('invoice_date') if invoice_date else None
    if not invoice_date:
        invoice_date, date_label, _index = _after_label(
            lines, DATE_LABEL_RES, date_finder,
            skip=lambda line: any(regex.search(line) for regex in DUE_LABEL_RES))
    if not invoice_date:
        dates = [found for found in find_dates(text, date_order) if found[0] != due]
        invoice_date = dates[0][0] if dates else None
    if invoice_date and due and due < invoice_date:
        due = None
    result.update(invoice_date=invoice_date, invoice_date_label=date_label, invoice_date_due=due,
                  invoice_date_due_label=due_label)
    # whether the numeric dates could be read both ways: the printed order of the vendor is then worth learning
    result['ambiguous_dates'] = any(kind for _value, _start, kind in find_dates(text, date_order))

    totals = _totals(lines, decimals)
    if anchors.get('amount_total'):
        anchored_total = _anchored(lines, anchors['amount_total'],
                                   lambda rest: (find_amounts(rest, decimals) or [[None]])[-1][0])
        if anchored_total and anchored_total != totals['amount_total']:
            totals.update(amount_total=anchored_total, totals_consistent=False)
            if totals['amount_untaxed'] and totals['amount_untaxed'] <= anchored_total:
                totals['amount_tax'] = round(anchored_total - totals['amount_untaxed'], 2)
                totals['totals_consistent'] = True
    result.update(totals)
    result['total_guessed'] = False
    if result['amount_total'] is None:
        # no total label the parser knows: the largest amount printed with its decimals, to be checked
        decimal_amounts = [value for value, start, end in find_amounts(text, decimals)
                           if re.search(r'[.,]\d{2,3}\)?$', text[start:end]) and value > 0]
        if decimal_amounts:
            result.update(amount_total=max(decimal_amounts), total_guessed=True)

    rows = find_lines(lines, decimals)
    net = result['amount_untaxed']
    if net is None and result['amount_total'] is not None and result['amount_tax'] is not None:
        net = result['amount_total'] - result['amount_tax']
    rows_total = round(sum(row['amount'] for row in rows), decimals)
    rows_ok = bool(rows) and (
        (net is not None and close(rows_total, net, 0.011 * len(rows)))
        or (net is None and result['amount_total'] is not None and close(rows_total, result['amount_total'], 0.011 * len(rows)))
    )
    result['lines'] = rows if rows_ok else []
    if rows_ok and result['amount_total'] is not None and result['amount_tax'] is not None \
            and close(rows_total + result['amount_tax'], result['amount_total'], 0.011 * len(rows)):
        result['totals_consistent'] = True
    if rows_ok and result['amount_untaxed'] is None:
        result['amount_untaxed'] = rows_total
        if result['amount_total'] is not None:
            result['amount_tax'] = round(result['amount_total'] - rows_total, decimals)

    po, _label, _index = _after_label(lines, PO_LABEL_RES, _reference_finder)
    result['po'] = po if po and po != reference else None
    result['vat_numbers'] = find_vat_numbers(text)
    result['ibans'] = find_ibans(text)
    result['emails'] = find_emails(text)
    result['header_lines'] = header_lines(text)
    result['currency'] = find_currency(text, known_currencies)
    result['is_refund'] = bool(re.search(r'credit\s*note|avoir|gutschrift|nota\s*de\s*cr[ée]dito|refund',
                                         '\n'.join(lines[:25]), re.IGNORECASE))
    return result


def label_at(text, position, length=0):
    """ The label printed before the value at `position` of the text: the words just before it on its line, or
    the ones above it when the value stands alone under its label. Used to learn where a vendor prints its
    fields. """
    line_start = text.rfind('\n', 0, position) + 1
    column = position - line_start
    # a currency printed before the amount is not its label: Amount Due USD 477.38
    before = re.sub(r'(?:\s*(?:\b[A-Z]{3}\b|[$€£₹¥]))+\s*$', '', text[line_start:position])
    before = re.split(r'\s{3,}', before.rstrip())[-1] if before.strip() else ''
    before = before.strip(' :#.-\t')
    if not before and line_start > 0:
        above_start = text.rfind('\n', 0, line_start - 1) + 1
        above = text[above_start:line_start - 1]
        before = above[max(0, column - 4):column + length + 20].strip(' :#.-\t')
        before = re.split(r'\s{3,}', before)[0] if before else ''
    words = before.split()
    if words and re.search(r'[A-Za-zÀ-ÿ]{2}', before):
        label = ' '.join(words[-4:])
        if len(label) <= 40:
            return label
    return None


def label_before(text, value_texts):
    """ The label printed before the first of the values found in the text. """
    for value_text in value_texts:
        if value_text and (position := text.find(value_text)) >= 0:
            return label_at(text, position, len(value_text))
    return None


def date_positions(text, value, date_order='dmy'):
    """ Where a date is printed in the text, whichever way it is written. """
    positions = []
    for order in ('dmy', 'mdy'):
        for found, start, kind in find_dates(text, order):
            if found == value:
                positions.append((start, kind and order))
    return positions


def amount_positions(text, value, decimals=2):
    """ Where an amount is printed in the text. """
    return [start for found, start, _end in find_amounts(text, decimals) if close(found, value, 0.005)]
