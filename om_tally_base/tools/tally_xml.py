""" Reading the XML of Tally: the files the user exports (Export > XML) and the answers of Tally to Export requests.

Tally writes XML that standard parsers refuse: character references to control characters (&#4;), raw control
characters, namespace prefixes without their declaration (UDF:...), lone '&', and UTF-16 files with or without
a byte order mark. ``sanitize_tally_text`` cleans these, then lxml reads the text in recover mode.

``iter_tally_objects`` reads the XML piece by piece (a file of any size never sits in memory whole) and yields
plain dicts per kind of record (no ORM here), so the same code reads a file and an answer of Tally.
"""
import codecs
import io
import re

from lxml import etree

from .tally_values import (
    tally_bool, tally_date, tally_debit, tally_due_date, tally_number, tally_quantity, tally_rate,
)

CHAR_REF = re.compile(r'&#(x[0-9a-fA-F]+|[0-9]+);')
CONTROL_CHARS = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]')
LONE_AMPERSAND = re.compile(r'&(?!(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);)')
TAG_PREFIX = re.compile(r'(</?)([A-Za-z_][\w.\-]*):(?=[A-Za-z_])')
XMLNS_ATTR = re.compile(r'\s+xmlns(?::[\w.\-]+)?\s*=\s*"[^"]*"')
XML_DECLARATION = re.compile(r'^\s*<\?xml[^>]*\?>')

MASTER_TAGS = (
    'COMPANY', 'GROUP', 'LEDGER', 'VOUCHERTYPE', 'COSTCATEGORY', 'COSTCENTRE', 'CURRENCY', 'UNIT',
    'STOCKGROUP', 'STOCKCATEGORY', 'STOCKITEM', 'GODOWN',
)
OBJECT_TAGS = MASTER_TAGS + ('VOUCHER',)


class TallyXmlError(Exception):
    pass


def decode_tally_bytes(data):
    """ The text of a Tally file or answer: UTF-16 (Tally's default for exports), UTF-8, or ANSI. """
    if isinstance(data, str):
        return data
    data = bytes(data)
    if data.startswith(b'\xff\xfe') or data.startswith(b'\xfe\xff'):
        return data.decode('utf-16', errors='replace')
    if data.startswith(b'\xef\xbb\xbf'):
        return data[3:].decode('utf-8', errors='replace')
    sample = data[:200]
    if len(sample) > 3 and sample.count(b'\x00') > len(sample) // 3:
        # UTF-16 without a byte order mark: the zero bytes tell the order
        return data.decode('utf-16-be' if sample[0] == 0 else 'utf-16-le', errors='replace')
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return data.decode('cp1252', errors='replace')


def _valid_reference(match):
    reference = match.group(1)
    try:
        code = int(reference[1:], 16) if reference[0] in 'xX' else int(reference)
    except ValueError:
        return ''
    if code in (9, 10, 13) or 32 <= code <= 0xD7FF or 0xE000 <= code <= 0xFFFD or 0x10000 <= code <= 0x10FFFF:
        return match.group(0)
    return ''


def sanitize_tally_text(text):
    """ Text that lxml reads: without the characters XML forbids, the undeclared prefixes and lone '&'. """
    text = XML_DECLARATION.sub('', text.lstrip('\ufeff'))
    text = CHAR_REF.sub(_valid_reference, text)
    text = CONTROL_CHARS.sub('', text)
    text = LONE_AMPERSAND.sub('&amp;', text)
    text = XMLNS_ATTR.sub('', text)
    text = TAG_PREFIX.sub(r'\1\2_', text)
    return text


# ------------------------------------------------------------------------------------------------------------
# helpers on elements

def _text(element, *paths):
    """ The first non-empty text among the paths. """
    for path in paths:
        value = element.findtext(path)
        if value and value.strip():
            return value.strip()
    return ''


def _texts(element, path):
    return [(el.text or '').strip() for el in element.findall(path) if (el.text or '').strip()]


def _name(element):
    """ The name of a master: the NAME attribute, the NAME tag, or the first name of LANGUAGENAME.LIST. """
    name = (element.get('NAME') or '').strip()
    if name:
        return name
    names = _texts(element, 'LANGUAGENAME.LIST/NAME.LIST/NAME')
    return names[0] if names else _text(element, 'NAME')


def _aliases(element, name):
    names = _texts(element, 'LANGUAGENAME.LIST/NAME.LIST/NAME')
    return ', '.join(alias for alias in names if alias != name)


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _common(element):
    name = _name(element)
    return {
        'name': name,
        'guid': _text(element, 'GUID'),
        'alter_id': _int(element.findtext('ALTERID')),
        'master_id': _int(element.findtext('MASTERID')),
        'reserved_name': (element.get('RESERVEDNAME') or '').strip(),
        'aliases': _aliases(element, name),
        'action': (element.get('ACTION') or '').strip().lower(),
    }


def _address(element):
    lines = _texts(element, 'ADDRESS.LIST/ADDRESS') or _texts(element, 'LEDMAILINGDETAILS.LIST/ADDRESS.LIST/ADDRESS')
    return '\n'.join(lines)


# ------------------------------------------------------------------------------------------------------------
# records

def _company(element):
    values = _common(element)
    values.update({
        'books_from': tally_date(_text(element, 'BOOKSFROM')),
        'starting_from': tally_date(_text(element, 'STARTINGFROM')),
        'currency_symbol': _text(element, 'BASECURRENCYSYMBOL', 'BASICCURRENCYSYMBOL', 'CURRENCYSYMBOL'),
        'currency_name': _text(element, 'CURRENCYNAME', 'BASECURRENCYNAME', 'FORMALNAME'),
        'gstin': _text(element, 'GSTREGISTRATIONNUMBER', 'GSTIN', 'GSTREGDETAILS.LIST/GSTIN',
                       'TAXREGISTRATIONNUMBER', 'VATTINNUMBER'),
        'state_name': _text(element, 'STATENAME', 'STATE'),
        'country_name': _text(element, 'COUNTRYNAME', 'COUNTRY'),
        'pincode': _text(element, 'PINCODE'),
        'email': _text(element, 'EMAIL'),
        'phone': _text(element, 'PHONENUMBER', 'PHONE'),
        'address': _address(element),
        'mailing_name': _text(element, 'MAILINGNAME', 'BASICCOMPANYFORMALNAME'),
        'pan': _text(element, 'INCOMETAXNUMBER', 'PANNUMBER'),
    })
    return values


def _group(element):
    values = _common(element)
    values.update({
        'parent_name': _text(element, 'PARENT'),
        'is_revenue': tally_bool(element.findtext('ISREVENUE')),
        'affects_gross_profit': tally_bool(element.findtext('AFFECTSGROSSPROFIT')),
        'is_deemed_positive': tally_bool(element.findtext('ISDEEMEDPOSITIVE')),
        'is_billwise': tally_bool(element.findtext('ISBILLWISEON')),
        'is_subledger': tally_bool(element.findtext('ISSUBLEDGER')),
    })
    return values


def _bill_openings(element):
    bills = []
    for bill in element.findall('BILLALLOCATIONS.LIST'):
        name = _text(bill, 'NAME')
        amount = tally_debit(bill.findtext('OPENINGBALANCE') or bill.findtext('AMOUNT'))
        if not name and not amount:
            continue
        bill_date = tally_date(_text(bill, 'BILLDATE'))
        credit_period = _text(bill, 'BILLCREDITPERIOD')
        bills.append({
            'name': name or 'Opening',
            'bill_date': bill_date,
            'credit_period': credit_period,
            'due_date': tally_due_date(bill_date, credit_period),
            'amount': amount,
            'is_advance': tally_bool(bill.findtext('ISADVANCE')),
        })
    return bills


def _ledger(element):
    values = _common(element)
    gst_details = element.find('LEDGSTREGDETAILS.LIST')
    mailing = element.find('LEDMAILINGDETAILS.LIST')
    values.update({
        'parent_name': _text(element, 'PARENT'),
        'opening_balance': tally_debit(element.findtext('OPENINGBALANCE')),
        'closing_balance': tally_debit(element.findtext('CLOSINGBALANCE')),
        'currency_name': _text(element, 'CURRENCYNAME'),
        'is_billwise': tally_bool(element.findtext('ISBILLWISEON')),
        'is_cost_centres_on': tally_bool(element.findtext('ISCOSTCENTRESON')),
        'credit_period': _text(element, 'BILLCREDITPERIOD'),
        'mailing_name': _text(element, 'MAILINGNAME') or (_text(mailing, 'MAILINGNAME') if mailing is not None else ''),
        'address': _address(element),
        'state_name': _text(element, 'LEDSTATENAME', 'STATENAME', 'PRIORSTATENAME')
        or (_text(mailing, 'STATE') if mailing is not None else ''),
        'country_name': _text(element, 'COUNTRYNAME', 'COUNTRYOFRESIDENCE')
        or (_text(mailing, 'COUNTRY') if mailing is not None else ''),
        'pincode': _text(element, 'PINCODE') or (_text(mailing, 'PINCODE') if mailing is not None else ''),
        'email': _text(element, 'EMAIL'),
        'phone': _text(element, 'LEDGERPHONE', 'PHONENUMBER'),
        'mobile': _text(element, 'LEDGERMOBILE', 'MOBILENUMBER'),
        'contact': _text(element, 'LEDGERCONTACT', 'CONTACTPERSON'),
        'website': _text(element, 'WEBSITE'),
        'gstin': _text(element, 'PARTYGSTIN', 'GSTIN')
        or (_text(gst_details, 'GSTIN') if gst_details is not None else ''),
        'gst_registration_type': _text(element, 'GSTREGISTRATIONTYPE')
        or (_text(gst_details, 'GSTREGISTRATIONTYPE') if gst_details is not None else ''),
        'vat_number': _text(element, 'VATTINNUMBER', 'TAXREGISTRATIONNUMBER', 'TRNNUMBER'),
        'pan': _text(element, 'INCOMETAXNUMBER'),
        'tax_type': _text(element, 'TAXTYPE'),
        'gst_duty_head': _text(element, 'GSTDUTYHEAD'),
        'tax_rate': abs(tally_number(element.findtext('RATEOFTAXCALCULATION'))),
        'bank_account_number': _text(element, 'BANKDETAILS', 'BANKACCOUNTNUMBER', 'ACCOUNTNUMBER'),
        'bank_ifsc': _text(element, 'IFSCODE', 'IFSCCODE'),
        'bank_name': _text(element, 'BANKINGCONFIGBANK', 'BANKNAME', 'BRANCHNAME'),
        'bills': _bill_openings(element),
    })
    return values


def _voucher_type(element):
    values = _common(element)
    values.update({
        'parent_name': _text(element, 'PARENT'),
        'numbering_method': _text(element, 'NUMBERINGMETHOD'),
        'is_active': not tally_bool(element.findtext('ISDEACTIVATED')) and element.findtext('ISACTIVE') != 'No',
        'is_optional_default': tally_bool(element.findtext('ISOPTIONAL')),
        'affects_stock': tally_bool(element.findtext('AFFECTSSTOCK')),
    })
    return values


def _cost_category(element):
    values = _common(element)
    values['allocate_revenue'] = tally_bool(element.findtext('ALLOCATEREVENUE'))
    values['allocate_non_revenue'] = tally_bool(element.findtext('ALLOCATENONREVENUE'))
    return values


def _cost_centre(element):
    values = _common(element)
    values.update({
        'parent_name': _text(element, 'PARENT'),
        'category_name': _text(element, 'CATEGORY') or 'Primary Cost Category',
    })
    return values


def _currency(element):
    values = _common(element)
    values.update({
        'formal_name': _text(element, 'MAILINGNAME', 'EXPANDEDSYMBOL', 'ORIGINALNAME'),
        'iso_code': _text(element, 'ISOCURRENCYCODE', 'ISOCODE'),
        'decimal_places': _int(element.findtext('DECIMALPLACES')),
    })
    return values


def _unit(element):
    values = _common(element)
    values.update({
        'formal_name': _text(element, 'ORIGINALNAME', 'FORMALNAME'),
        'is_simple': element.findtext('ISSIMPLEUNIT') != 'No',
        'base_unit_name': _text(element, 'BASEUNITS'),
        'additional_unit_name': _text(element, 'ADDITIONALUNITS'),
        'conversion': abs(tally_number(element.findtext('CONVERSION'))) or 1.0,
        'decimal_places': _int(element.findtext('DECIMALPLACES')),
        'uqc': _text(element, 'GSTREPUOM', 'UQC'),
    })
    return values


def _stock_group(element):
    values = _common(element)
    values['parent_name'] = _text(element, 'PARENT')
    return values


def _stock_item(element):
    values = _common(element)
    openings = []
    for batch in element.findall('BATCHALLOCATIONS.LIST'):
        quantity, unit = tally_quantity(batch.findtext('OPENINGBALANCE'))
        value = tally_debit(batch.findtext('OPENINGVALUE'))
        if not quantity and not value:
            continue
        openings.append({
            'godown_name': _text(batch, 'GODOWNNAME') or 'Main Location',
            'batch_name': _text(batch, 'BATCHNAME'),
            'quantity': quantity,
            'unit_name': unit,
            'value': value,
            'rate': tally_rate(batch.findtext('OPENINGRATE')),
            'manufacturing_date': tally_date(_text(batch, 'MFDON', 'MANUFACTUREDON')),
            'expiry_date': tally_date(_text(batch, 'EXPIRYPERIOD', 'EXPIRYDATE')),
        })
    quantity, unit = tally_quantity(element.findtext('OPENINGBALANCE'))
    hsn = _text(element, 'HSNCODE', 'GSTDETAILS.LIST/HSNCODE', 'HSNDETAILS.LIST/HSNCODE',
                'GSTDETAILS.LIST/HSNMASTERNAME')
    gst_rate = 0.0
    for rate_details in element.iter('RATEDETAILS.LIST'):
        if _text(rate_details, 'GSTRATEDUTYHEAD') in ('Integrated Tax', 'IGST'):
            gst_rate = abs(tally_number(rate_details.findtext('GSTRATE')))
    values.update({
        'parent_name': _text(element, 'PARENT'),
        'category_name': _text(element, 'CATEGORY'),
        'base_unit_name': _text(element, 'BASEUNITS'),
        'additional_unit_name': _text(element, 'ADDITIONALUNITS'),
        'part_number': _text(element, 'MAILINGNAME.LIST/MAILINGNAME', 'PARTNUMBER', 'PARTNO'),
        'description': _text(element, 'DESCRIPTION', 'NARRATION'),
        'hsn_code': hsn,
        'gst_rate': gst_rate or abs(tally_number(element.findtext('GSTRATE'))),
        'gst_applicable': _text(element, 'GSTAPPLICABLE').lstrip('\x04 ').strip(),
        'is_batchwise': tally_bool(element.findtext('ISBATCHWISEON')),
        'has_expiry': tally_bool(element.findtext('ISPERISHABLEON')),
        'costing_method': _text(element, 'COSTINGMETHOD'),
        'opening_quantity': quantity,
        'opening_unit_name': unit,
        'opening_value': tally_debit(element.findtext('OPENINGVALUE')),
        'opening_rate': tally_rate(element.findtext('OPENINGRATE')),
        'openings': openings,
    })
    return values


def _godown(element):
    values = _common(element)
    values.update({
        'parent_name': _text(element, 'PARENT'),
        'address': _address(element),
    })
    return values


def _ledger_line(entry, from_inventory=False):
    bills = []
    for bill in entry.findall('BILLALLOCATIONS.LIST'):
        name = _text(bill, 'NAME')
        bill_type = _text(bill, 'BILLTYPE') or ('Agst Ref' if name else 'On Account')
        amount = tally_debit(bill.findtext('AMOUNT'))
        if not amount:
            continue
        credit_period = _text(bill, 'BILLCREDITPERIOD')
        bills.append({'name': name, 'bill_type': bill_type, 'amount': amount, 'credit_period': credit_period})
    costs = []
    for category in entry.findall('CATEGORYALLOCATIONS.LIST'):
        category_name = _text(category, 'CATEGORY') or 'Primary Cost Category'
        for centre in category.findall('COSTCENTREALLOCATIONS.LIST'):
            amount = tally_debit(centre.findtext('AMOUNT'))
            if amount:
                costs.append({'category_name': category_name, 'name': _text(centre, 'NAME'), 'amount': amount})
    bank = entry.find('BANKALLOCATIONS.LIST')
    return {
        'ledger_name': _text(entry, 'LEDGERNAME'),
        'amount': tally_debit(entry.findtext('AMOUNT')),
        'is_deemed_positive': tally_bool(entry.findtext('ISDEEMEDPOSITIVE')),
        'is_party': tally_bool(entry.findtext('ISPARTYLEDGER')),
        'from_inventory': from_inventory,
        'instrument_number': _text(bank, 'INSTRUMENTNUMBER') if bank is not None else '',
        'instrument_date': tally_date(_text(bank, 'INSTRUMENTDATE')) if bank is not None else False,
        'bills': bills,
        'costs': costs,
    }


def _inventory_lines(entry, inward_default):
    item = _text(entry, 'STOCKITEMNAME')
    deemed = entry.findtext('ISDEEMEDPOSITIVE')
    inward = tally_bool(deemed) if deemed is not None else inward_default
    rate = tally_rate(entry.findtext('RATE'))
    discount = abs(tally_number(entry.findtext('DISCOUNT')))
    ledger = _text(entry, 'ACCOUNTINGALLOCATIONS.LIST/LEDGERNAME')
    lines = []
    batches = entry.findall('BATCHALLOCATIONS.LIST')
    for batch in batches or [entry]:
        quantity, unit = tally_quantity(batch.findtext('BILLEDQTY') or batch.findtext('ACTUALQTY'))
        if not quantity and batch is not entry:
            quantity, unit = tally_quantity(batch.findtext('ACTUALQTY'))
        amount = tally_number(batch.findtext('AMOUNT'))
        lines.append({
            'item_name': item,
            'quantity': abs(quantity),
            'unit_name': unit,
            'rate': rate or (abs(amount / quantity) if quantity else 0.0),
            'discount': discount,
            'amount': abs(amount),
            'is_inward': inward,
            'godown_name': _text(batch, 'GODOWNNAME') if batch is not entry else '',
            'batch_name': _text(batch, 'BATCHNAME') if batch is not entry else '',
            'ledger_name': ledger,
        })
    return lines


def _voucher(element):
    values = _common(element)
    type_name = _text(element, 'VOUCHERTYPENAME') or (element.get('VCHTYPE') or '').strip()
    lines = []
    entries = element.findall('ALLLEDGERENTRIES.LIST') or element.findall('LEDGERENTRIES.LIST')
    lines += [_ledger_line(entry) for entry in entries]
    inventory = []
    for tag, inward in (('ALLINVENTORYENTRIES.LIST', None), ('INVENTORYENTRIES.LIST', None),
                        ('INVENTORYENTRIESIN.LIST', True), ('INVENTORYENTRIESOUT.LIST', False)):
        found = element.findall(tag)
        if tag == 'INVENTORYENTRIES.LIST' and element.findall('ALLINVENTORYENTRIES.LIST'):
            continue
        for entry in found:
            inventory += _inventory_lines(entry, bool(inward))
            lines += [_ledger_line(allocation, from_inventory=True)
                      for allocation in entry.findall('ACCOUNTINGALLOCATIONS.LIST')]
    lines = [line for line in lines if line['ledger_name'] and line['amount']]
    values.update({
        'guid': values['guid'] or (element.get('REMOTEID') or '').strip(),
        'date': tally_date(_text(element, 'DATE')),
        'effective_date': tally_date(_text(element, 'EFFECTIVEDATE')),
        'voucher_type_name': type_name,
        'number': _text(element, 'VOUCHERNUMBER'),
        'reference': _text(element, 'REFERENCE'),
        'reference_date': tally_date(_text(element, 'REFERENCEDATE')),
        'party_name': _text(element, 'PARTYLEDGERNAME', 'PARTYNAME'),
        'narration': _text(element, 'NARRATION'),
        'is_cancelled': tally_bool(element.findtext('ISCANCELLED')),
        'is_optional': tally_bool(element.findtext('ISOPTIONAL')),
        'is_postdated': tally_bool(element.findtext('ISPOSTDATED')),
        'is_invoice': tally_bool(element.findtext('ISINVOICE')),
        'is_deleted': tally_bool(element.findtext('ISDELETED')) or values['action'] == 'delete',
        'view': _text(element, 'PERSISTEDVIEW') or (element.get('OBJVIEW') or '').strip(),
        'lines': lines,
        'inventory': inventory,
    })
    return values


READERS = {
    'COMPANY': _company,
    'GROUP': _group,
    'LEDGER': _ledger,
    'VOUCHERTYPE': _voucher_type,
    'COSTCATEGORY': _cost_category,
    'COSTCENTRE': _cost_centre,
    'CURRENCY': _currency,
    'UNIT': _unit,
    'STOCKGROUP': _stock_group,
    'STOCKCATEGORY': _stock_group,
    'STOCKITEM': _stock_item,
    'GODOWN': _godown,
    'VOUCHER': _voucher,
}


class _Decoder:
    """ Decodes a stream of bytes of Tally: UTF-16 (with or without a byte order mark), UTF-8, or ANSI. """

    def __init__(self, head):
        if head.startswith((b'\xff\xfe', b'\xfe\xff')):
            encoding = 'utf-16'
        elif head.startswith(b'\xef\xbb\xbf'):
            encoding = 'utf-8-sig'
        else:
            sample = head[:200]
            if len(sample) > 3 and sample.count(b'\x00') > len(sample) // 3:
                encoding = 'utf-16-be' if sample[0] == 0 else 'utf-16-le'
            else:
                encoding = 'utf-8'
        self.decoder = codecs.getincrementaldecoder(encoding)(errors='strict' if encoding == 'utf-8' else 'replace')

    def decode(self, data, final):
        try:
            return self.decoder.decode(data, final)
        except UnicodeDecodeError:
            # an ANSI export
            self.decoder = codecs.getincrementaldecoder('cp1252')(errors='replace')
            return self.decoder.decode(data, final)


def _clear(element):
    """ Free a parsed element and the siblings before it. """
    element.clear()
    parent = element.getparent()
    if parent is not None:
        while element.getprevious() is not None:
            del parent[0]


def iter_tally_objects(source, chunk_size=1 << 20):
    """ Yield (tag, values) for each record of Tally XML read from bytes, text or a binary file, piece by piece.
    Also yields ('current_company', name) and ('errors', [message]) when the XML says so. """
    if isinstance(source, str):
        stream = io.BytesIO(source.encode('utf-8'))
    elif isinstance(source, (bytes, bytearray, memoryview)):
        stream = io.BytesIO(bytes(source))
    else:
        stream = source
    parser = etree.XMLPullParser(events=('start', 'end'), recover=True, huge_tree=True, resolve_entities=False,
                                 no_network=True, remove_blank_text=True)
    decoder, carry, started, depth, status_zero, errors = None, '', False, 0, False, []
    while True:
        data = stream.read(chunk_size)
        final = not data
        if decoder is None:
            if final:
                raise TallyXmlError("The file is empty.")
            decoder = _Decoder(data)
        text = carry + decoder.decode(data, final)
        if final:
            carry = ''
        else:
            # cut after the last tag: references and tags are never split between two pieces
            cut = text.rfind('>') + 1
            text, carry = text[:cut], text[cut:]
        if not started:
            text = XML_DECLARATION.sub('', text.lstrip('\ufeff \r\n\t')).lstrip()
            if not text:
                if final:
                    raise TallyXmlError("The file is empty.")
                continue
            if not text.startswith('<'):
                raise TallyXmlError("This is not XML: export the data from Tally in XML format.")
            started = True
        if text:
            parser.feed(sanitize_tally_text(text).encode('utf-8'))
        if final:
            try:
                parser.close()
            except etree.XMLSyntaxError:
                pass
        for event, element in parser.read_events():
            tag = element.tag
            if event == 'start':
                if tag in OBJECT_TAGS:
                    depth += 1
                continue
            if tag in OBJECT_TAGS:
                depth -= 1
                if depth == 0:
                    if _name(element) or tag == 'VOUCHER':
                        yield tag, READERS[tag](element)
                    _clear(element)
            elif depth == 0:
                if tag == 'SVCURRENTCOMPANY' and (element.text or '').strip():
                    yield 'current_company', element.text.strip()
                elif tag == 'LINEERROR' and (element.text or '').strip():
                    errors.append(element.text.strip())
                elif tag == 'STATUS' and (element.text or '').strip() == '0' and \
                        element.getparent() is not None and element.getparent().tag == 'HEADER':
                    status_zero = True
                elif tag == 'TALLYMESSAGE':
                    _clear(element)
        if final:
            break
    if status_zero and not errors:
        errors.append("Tally refused the request.")
    if errors:
        yield 'errors', errors


def read_tally_objects(source):
    """ {tag: [dict]} of the records in Tally XML (bytes, text or a binary file), with 'current_company' and
    'errors'. """
    result = {tag: [] for tag in OBJECT_TAGS}
    result.update(current_company='', errors=[])
    for tag, values in iter_tally_objects(source):
        if tag == 'current_company':
            result['current_company'] = result['current_company'] or values
        elif tag == 'errors':
            result['errors'] += values
        else:
            result[tag].append(values)
    return result
