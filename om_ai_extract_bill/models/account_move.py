import logging

from odoo import fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.om_account_bill_ocr.tools import bill_parser

_logger = logging.getLogger(__name__)

LOW_CONFIDENCE = 0.7
BILL_PROPERTIES = {
    'vendor_name': {'type': ['string', 'null'], 'description': 'Name of the company that issued the bill'},
    'vendor_vat': {'type': ['string', 'null'], 'description': 'Tax number of the vendor (not of the customer)'},
    'vendor_iban': {'type': ['string', 'null'], 'description': 'Bank account of the vendor to pay to'},
    'vendor_email': {'type': ['string', 'null']},
    'bill_number': {'type': ['string', 'null'], 'description': 'Invoice number printed by the vendor'},
    'bill_date': {'type': ['string', 'null'], 'format': 'date'},
    'due_date': {'type': ['string', 'null'], 'format': 'date'},
    'currency': {'type': ['string', 'null'], 'description': 'ISO code, e.g. EUR'},
    'purchase_order': {'type': ['string', 'null'], 'description': 'Our order reference if printed'},
    'is_credit_note': {'type': ['boolean', 'null']},
    'amount_untaxed': {'type': ['number', 'null']},
    'amount_tax': {'type': ['number', 'null']},
    'amount_total': {'type': ['number', 'null']},
    'lines': {
        'type': 'array',
        'items': {
            'type': 'object',
            'properties': {
                'description': {'type': ['string', 'null']},
                'quantity': {'type': ['number', 'null']},
                'unit_price': {'type': ['number', 'null'], 'description': 'Price per unit without tax'},
                'amount': {'type': ['number', 'null'], 'description': 'Line total without tax'},
            },
            'required': ['description', 'quantity', 'unit_price', 'amount'],
            'additionalProperties': False,
        },
    },
}
INSTRUCTIONS = """Read this vendor bill (or credit note) received by %(company)s. %(company)s is the customer: never
give its name, tax number or bank account as the vendor's. Give the lines of the bill table without tax, and the
untaxed amount, the taxes and the total as printed."""


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _om_ocr_decode(self, file_data, new=False):
        self.ensure_one()
        if self.company_id.om_bill_ocr_engine != 'ai' or self.invoice_line_ids:
            return super()._om_ocr_decode(file_data, new)
        try:
            return self._om_ai_decode(file_data)
        except (UserError, AccessError) as error:
            message = str(error.args[0] if error.args else error)
            if self.company_id.om_bill_ai_fallback:
                self.message_post(body=self.env._('The AI could not read the bill (%s): it was read on the server.',
                                                  message))
                return super()._om_ocr_decode(file_data, new)
            return self.env._('the AI could not read the bill: %s', message)

    def _om_ai_decode(self, file_data):
        Extract = self.env['om.ai.extract']
        own_names = ', '.join(self.env['res.company'].sudo().search([]).mapped('name'))
        schema = Extract._schema(BILL_PROPERTIES, required=list(BILL_PROPERTIES))
        data, problems, payload = Extract._extract(
            file_data['raw'], file_data.get('mimetype'), file_data.get('name'), schema,
            instructions=INSTRUCTIONS % {'company': own_names})
        parsed, checks = self._om_ai_bill_parsed(data)
        text = payload['text'] or self._om_ai_bill_text(data)
        self.with_context(om_ai_bill_vendor=data.get('vendor_name'))._om_ocr_fill(text, 'ai', parsed=parsed)
        notes = list(data['flags']) + problems + checks
        if data.get('confidence') is not None and data['confidence'] < LOW_CONFIDENCE:
            notes.append(self.env._('The AI is not sure of this reading.'))
        to_check = [item for item in (self.om_ocr_to_check or '').split(', ') if item]
        if notes:
            to_check.append(self.env._('AI Notes'))
        self.write({
            'om_ocr_state': 'to_check' if to_check else 'done',
            'om_ocr_to_check': ', '.join(dict.fromkeys(to_check)) or False,
            'om_ocr_data': dict(self.om_ocr_data or {}, learn_labels=bool(payload['text']),
                                ai_confidence=data.get('confidence'), ai_source=payload['source']),
        })
        self.message_post(body=Extract._summary_html(data, problems, checks))
        return None

    def _om_ai_bill_parsed(self, data):
        """The AI answer in the format of the bill parser of Vendor Bill OCR, and the checks that failed."""
        checks = []
        decimals = self.company_id.currency_id.decimal_places
        total, untaxed, tax = data.get('amount_total'), data.get('amount_untaxed'), data.get('amount_tax')
        if untaxed is None and total is not None and tax is not None:
            untaxed = round(total - tax, decimals)
        if tax is None and total is not None and untaxed is not None:
            tax = round(total - untaxed, decimals)
        consistent = None not in (total, untaxed, tax) and bill_parser.close(untaxed + tax, total)
        if None not in (total, untaxed, tax) and not consistent:
            checks.append(self.env._('Untaxed amount plus taxes is not the total read.'))
        rows = []
        for line in data.get('lines') or []:
            quantity = line.get('quantity') or 1.0
            price = line.get('unit_price')
            amount = line.get('amount')
            if price is None and amount is not None:
                price = amount / quantity if quantity else amount
            if price is None:
                continue
            rows.append({'name': line.get('description') or '/', 'quantity': quantity, 'price_unit': price,
                         'amount': round(amount if amount is not None else quantity * price, decimals)})
        if rows:
            rows_total = round(sum(row['amount'] for row in rows), decimals)
            reference = untaxed if untaxed is not None else total
            if reference is None or not bill_parser.close(rows_total, reference, 0.011 * len(rows)):
                checks.append(self.env._('The lines read do not add up to the untaxed amount: the bill is booked on '
                                         'one line.'))
                rows = []
        return {
            'ref': data.get('bill_number'),
            'invoice_date': fields.Date.to_date(data['bill_date']) if data.get('bill_date') else None,
            'invoice_date_due': fields.Date.to_date(data['due_date']) if data.get('due_date') else None,
            'ambiguous_dates': False,
            'amount_total': total,
            'amount_untaxed': untaxed,
            'amount_tax': tax,
            'totals_consistent': consistent,
            'total_guessed': False,
            'lines': rows,
            'po': data.get('purchase_order'),
            'currency': (data.get('currency') or '').upper() or None,
            'is_refund': bool(data.get('is_credit_note')),
            'vat_numbers': [bill_parser.normalize_vat(data['vendor_vat'])] if data.get('vendor_vat') else [],
            'ibans': [bill_parser.normalize_vat(data['vendor_iban'])] if data.get('vendor_iban') else [],
            'emails': [data['vendor_email'].lower()] if data.get('vendor_email') else [],
            'header_lines': [data['vendor_name']] if data.get('vendor_name') else [],
        }, checks

    @staticmethod
    def _om_ai_bill_text(data):
        """A short text with the identifiers of the vendor, for a bill read from an image: the vendor is
        recognized from it as from the text of a PDF."""
        lines = [data.get('vendor_name') or '']
        if data.get('vendor_vat'):
            lines.append('VAT: %s' % data['vendor_vat'])
        if data.get('vendor_iban'):
            lines.append('IBAN: %s' % data['vendor_iban'])
        if data.get('vendor_email'):
            lines.append('Email: %s' % data['vendor_email'])
        return '\n'.join(lines)

    def _om_ocr_find_partner(self, text, info):
        partner, found_by = super()._om_ocr_find_partner(text, info)
        name = self.env.context.get('om_ai_bill_vendor')
        if partner or not name or len(name) < 3:
            return partner, found_by
        Partner = self.env['res.partner']
        domain = self._om_ocr_partner_domain()
        partners = Partner.search([*domain, ('name', '=ilike', name)], limit=2).commercial_partner_id
        if len(partners) != 1:
            partners = Partner.search([*domain, ('supplier_rank', '>', 0), ('name', 'ilike', name)],
                                      limit=2).commercial_partner_id
        if len(partners) == 1:
            return partners, 'name'
        return Partner, None

    def _om_ocr_source_text(self, source):
        if source == 'ai':
            return self.env._('The bill was read by your AI model.')
        return super()._om_ocr_source_text(source)
