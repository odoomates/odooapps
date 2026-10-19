import logging
import re
from collections import Counter

from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

from ..tools import bill_parser
from ..tools.text_extract import OcrUnavailable, extract_text, is_image

_logger = logging.getLogger(__name__)

# the mail domains shared by many senders: an email at one of them does not tell the vendor
PUBLIC_EMAIL_DOMAINS = {
    'gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.co.in', 'yahoo.fr', 'hotmail.com', 'hotmail.fr',
    'outlook.com', 'live.com', 'msn.com', 'icloud.com', 'me.com', 'aol.com', 'gmx.de', 'gmx.net', 'web.de',
    'orange.fr', 'free.fr', 'proton.me', 'protonmail.com', 'mail.com', 'yandex.com', 'zoho.com', 'rediffmail.com',
}
IMAGE_IMPORT_TYPE = 'om.bill.image'
# letterhead lines that every bill prints: never a key to a vendor
GENERIC_HEADER_RE = re.compile(
    r'^(?:(?:tax|vat|gst|proforma|pro-forma|commercial|original|duplicate|copy)\s+)*(?:invoice|bill|receipt|'
    r'credit\s*note|facture|rechnung|factura|statement|page\b.*|bill\s+to|ship\s+to|sold\s+to|invoice\s+to)\W*$',
    re.IGNORECASE)


class AccountMove(models.Model):
    _inherit = 'account.move'

    om_ocr_state = fields.Selection([
        ('done', "Read"),
        ('to_check', "Read, To Check"),
    ], string="Bill Recognition", copy=False, readonly=True, index='btree_not_null')
    om_ocr_to_check = fields.Char(string="Fields to Check", copy=False, readonly=True)
    om_ocr_text = fields.Text(string="Text of the Bill", copy=False, readonly=True)
    om_ocr_data = fields.Json(copy=False, readonly=True)
    om_ocr_can_read = fields.Boolean(compute='_compute_om_ocr_can_read')

    @api.depends('state', 'move_type', 'invoice_line_ids', 'attachment_ids')
    def _compute_om_ocr_can_read(self):
        for move in self:
            move.om_ocr_can_read = (
                move.state == 'draft'
                and move.is_purchase_document(include_receipts=True)
                and not move.invoice_line_ids
                and move.company_id.om_bill_ocr_mode != 'off'
                and bool(move._om_ocr_attachments())
            )

    # ------------------------------------------------------------------------------------------------------
    # the decoder of the upload
    # ------------------------------------------------------------------------------------------------------

    @api.model
    def _get_import_file_type(self, file_data):
        """ The photos and the scans of the bills are documents to read too. """
        file_type = super()._get_import_file_type(file_data)
        if not file_type and is_image(file_data.get('mimetype'), file_data.get('name')):
            return IMAGE_IMPORT_TYPE
        return file_type

    def _get_edi_decoder(self, file_data, new=False):
        """ A PDF or an image of a vendor bill is read, after the electronic invoices: a Factur-X or a UBL file
        is decoded by its own decoder, of a higher priority, and the PDF that carries it is not read. """
        decoder = super()._get_edi_decoder(file_data, new)
        if decoder:
            return decoder
        if file_data.get('import_file_type') in ('pdf', IMAGE_IMPORT_TYPE) and self._om_ocr_applies():
            return {
                'priority': 5,
                'decoder': lambda invoice, file_data, new: invoice._om_ocr_decode(file_data, new),
            }
        return None

    def _om_ocr_applies(self):
        """ Whether the uploaded documents are read: the vendor bills of a company reading them on upload. """
        if self:
            move = self[:1]
            return move.is_purchase_document(include_receipts=True) and move.company_id.om_bill_ocr_mode == 'auto'
        move_type = self.env.context.get('default_move_type')
        return move_type in self.get_purchase_types(include_receipts=True) \
            and self.env.company.om_bill_ocr_mode == 'auto'

    def _om_ocr_decode(self, file_data, new=False):
        self.ensure_one()
        if self.invoice_line_ids:
            return self._reason_cannot_decode_has_invoice_lines()
        try:
            text, source = extract_text(file_data['raw'], file_data.get('mimetype'), file_data.get('name'),
                                        self.company_id.om_bill_ocr_languages or 'eng')
        except OcrUnavailable:
            return self.env._(
                "this bill is a scan or a photo, and reading it needs Tesseract on the server: install the "
                "tesseract-ocr package (and poppler-utils for the scanned PDFs).")
        except Exception as error:  # noqa: BLE001 a tool failing on a file must not stop the upload
            _logger.warning("Bill recognition could not read %s", file_data.get('name'), exc_info=True)
            return self.env._("the bill could not be read: %(error)s", error=error)
        if len(''.join(text.split())) < 20:
            return self.env._("no text could be read on this bill.")
        self._om_ocr_fill(text, source)
        return None

    # ------------------------------------------------------------------------------------------------------
    # filling the bill
    # ------------------------------------------------------------------------------------------------------

    def _om_ocr_date_order(self, profile):
        if profile.date_order:
            return profile.date_order
        date_format = self.env['res.lang']._get_data(code=self.env.lang or 'en_US').date_format or '%m/%d/%Y'
        return 'mdy' if date_format.find('%m') < date_format.find('%d') else 'dmy'

    def _om_ocr_own_identifiers(self):
        """ The tax numbers and the bank accounts of the companies of the database: printed on the bill as its
        customer, they never tell the vendor. """
        companies = self.env['res.company'].sudo().search([])
        vats = {bill_parser.normalize_vat(vat) for vat in companies.mapped('vat') if vat}
        ibans = {bill_parser.normalize_vat(number) for number in
                 companies.partner_id.bank_ids.mapped('sanitized_account_number') if number}
        domains = {email.split('@')[-1].lower() for email in companies.mapped('email') if email and '@' in email}
        return vats, ibans, domains

    def _om_ocr_header_keys(self, info):
        """ The letterhead lines that can tell a vendor: not the title of the document, nor the name of the
        company receiving the bill. """
        own_names = {name.lower() for name in self.env['res.company'].sudo().search([]).mapped('name')}
        return [line for line in info['header_lines'][:6]
                if len(line) >= 6 and not GENERIC_HEADER_RE.match(line) and line.lower() not in own_names
                and not any(name in line.lower() for name in own_names)]

    def _om_ocr_partner_domain(self):
        return [
            *self.env['res.partner']._check_company_domain(self.company_id),
            ('id', 'not in', self.env['res.company'].sudo().search([]).partner_id.ids),
        ]

    def _om_ocr_find_partner(self, text, info):
        """ The vendor of the bill: by its tax number, its bank account, what its earlier bills taught, its
        email, then its name in the letterhead. Returns (partner, how it was found). """
        Partner = self.env['res.partner']
        own_vats, own_ibans, own_domains = self._om_ocr_own_identifiers()
        domain = self._om_ocr_partner_domain()
        vats = [vat for vat in info['vat_numbers'] if vat not in own_vats]
        ibans = [iban for iban in info['ibans'] if iban not in own_ibans]

        for vat in vats:
            digits = re.sub(r'^[A-Z]{1,3}', '', vat)
            if len(digits) < 5:
                continue
            for partner in Partner.search([*domain, ('vat', 'ilike', digits[-5:])], limit=20):
                partner_vat = bill_parser.normalize_vat(partner.vat)
                partner_digits = re.sub(r'^[A-Z]{1,3}', '', partner_vat)
                if partner_vat == vat or partner_digits == digits:
                    return partner.commercial_partner_id, 'vat'
        if ibans:
            bank = self.env['res.partner.bank'].search([
                ('sanitized_account_number', 'in', ibans),
                ('partner_id', 'any', domain),
            ], limit=1)
            if bank:
                return bank.partner_id.commercial_partner_id, 'iban'

        emails = [email for email in info['emails'] if email.split('@')[-1] not in own_domains]
        keys = vats + ibans + [email.split('@')[-1] for email in emails
                               if email.split('@')[-1] not in PUBLIC_EMAIL_DOMAINS] + self._om_ocr_header_keys(info)
        if keys:
            profiles = self.env['om.bill.ocr.profile'].search([('company_id', '=', self.company_id.id)])
            for profile in profiles:
                if profile._match_keys() & set(keys):
                    return profile.partner_id, 'learned'

        for email in emails:
            partner = Partner.search([*domain, ('email', '=ilike', email)], limit=1)
            if partner:
                return partner.commercial_partner_id, 'email'
        for email in emails:
            email_domain = email.split('@')[-1]
            if email_domain in PUBLIC_EMAIL_DOMAINS:
                continue
            partners = Partner.search([*domain, '|', ('email', '=ilike', f'%@{email_domain}'),
                                       ('website', 'ilike', email_domain)]).commercial_partner_id
            if len(partners) == 1:
                return partners, 'email'

        # the name of the company receiving the bill is printed on it too, as its customer: never the vendor
        own_names = [name.lower() for name in self.env['res.company'].sudo().search([]).mapped('name')]
        name_lines = [line for line in info['header_lines']
                      if not any(own in line.lower() or line.lower() in own for own in own_names)]
        for line in name_lines:
            name = line.strip()
            if len(name) < 3:
                continue
            partners = Partner.search([*domain, ('name', '=ilike', name)], limit=2).commercial_partner_id
            if len(partners) == 1:
                return partners, 'name'
        for line in name_lines[:6]:
            name = re.sub(r'\b(?:inc|ltd|llc|gmbh|sarl|sas|s\.?a|b\.?v|plc|pvt|private|limited|co)\b\.?', '',
                          line, flags=re.IGNORECASE).strip(' ,.')
            if len(name) < 5:
                continue
            partners = Partner.search([*domain, ('supplier_rank', '>', 0), ('name', 'ilike', name)],
                                      limit=2).commercial_partner_id
            if len(partners) == 1:
                return partners, 'name'
        return Partner, None

    def _om_ocr_last_bill_lines(self, partner):
        last_bill = self.search([
            *self._check_company_domain(self.company_id),
            ('partner_id', 'child_of', partner.id), ('state', '=', 'posted'),
            ('move_type', 'in', ('in_invoice', 'in_refund')), ('id', '!=', self.id),
        ], order='invoice_date desc, id desc', limit=1)
        return last_bill.invoice_line_ids.filtered(lambda line: line.display_type == 'product')

    def _om_ocr_tax_for_rate(self, untaxed, tax):
        """ The purchase tax whose rate gives the taxes printed on the bill. """
        if not untaxed or tax is None or float_is_zero(tax, precision_digits=2):
            return self.env['account.tax']
        rate = round(tax / untaxed * 100, 2)
        taxes = self.env['account.tax'].search([
            *self.env['account.tax']._check_company_domain(self.company_id),
            ('type_tax_use', '=', 'purchase'), ('amount_type', '=', 'percent'), ('price_include', '=', False),
            ('active', '=', True),
        ])
        matching = taxes.filtered(lambda t: abs(t.amount - rate) <= 0.06)
        # the tax of the company's default first: the one usually meant
        default = self.company_id.account_purchase_tax_id
        if default in matching:
            return default
        return matching[:1]

    def _om_ocr_fill(self, text, source):
        """ Fill the bill with what its text says, and say what is to be checked. """
        self.ensure_one()
        own_vats, own_ibans, own_domains = self._om_ocr_own_identifiers()
        preliminary = {
            'vat_numbers': bill_parser.find_vat_numbers(text),
            'ibans': bill_parser.find_ibans(text),
            'emails': bill_parser.find_emails(text),
            'header_lines': bill_parser.header_lines(text),
        }
        partner, found_by = self._om_ocr_find_partner(text, preliminary)
        profile = self.env['om.bill.ocr.profile']
        if partner:
            profile = profile._for_partner(partner, self.company_id)
        date_order = self._om_ocr_date_order(profile)
        currencies = self.env['res.currency'].search([])
        result = bill_parser.parse_bill(
            text, date_order=date_order, decimals=self.company_id.currency_id.decimal_places,
            anchors=profile._anchors() if profile else None, known_currencies=set(currencies.mapped('name')))
        to_check = []

        values = {}
        if partner:
            values['partner_id'] = partner.id
        else:
            to_check.append(self.env._("Vendor"))
        if result['ref']:
            values['ref'] = result['ref']
        else:
            to_check.append(self.env._("Bill Reference"))
        if result['invoice_date']:
            values['invoice_date'] = result['invoice_date']
            if result['ambiguous_dates'] and not profile.date_order:
                to_check.append(self.env._("Bill Date"))
        else:
            to_check.append(self.env._("Bill Date"))
        currency = result['currency'] and currencies.filtered(lambda c: c.name == result['currency'])[:1]
        if currency and currency.active and currency != self.currency_id:
            values['currency_id'] = currency.id
        if result['po']:
            values['invoice_origin'] = result['po']
        if result['is_refund'] and self.move_type == 'in_invoice':
            values['move_type'] = 'in_refund'

        total = result['amount_total']
        untaxed = result['amount_untaxed']
        tax = result['amount_tax']
        if untaxed is None and total is not None:
            untaxed = total - (tax or 0.0)

        # the account, the taxes and the product: what the vendor's bills taught, else its last bill, else the
        # purchase tax of the rate printed on the bill
        last_lines = self._om_ocr_last_bill_lines(partner) if partner else self.env['account.move.line']
        account = profile.account_id
        product = profile.product_id
        if not account and last_lines:
            account = Counter(last_lines.mapped('account_id')).most_common(1)[0][0]
        rate_tax = self._om_ocr_tax_for_rate(untaxed, tax)
        if profile.bill_count:
            taxes = profile.tax_ids
        elif last_lines:
            taxes = last_lines[:1].tax_ids
        else:
            taxes = rate_tax
        no_tax = tax is not None and float_is_zero(tax, precision_digits=2)
        if (no_tax and taxes) or (tax and not taxes) or (rate_tax and rate_tax not in taxes) or tax is None:
            to_check.append(self.env._("Taxes"))
        if not account and not product:
            to_check.append(self.env._("Account"))

        line_mode = 'lines' if result['lines'] and (not profile or profile.line_mode == 'lines') else 'single'
        line_values = []

        def line_vals(name, quantity, price_unit):
            vals = {'name': name, 'quantity': quantity, 'price_unit': price_unit, 'tax_ids': [Command.set(taxes.ids)]}
            if product:
                vals['product_id'] = product.id
            if account:
                vals['account_id'] = account.id
            return vals

        if line_mode == 'lines':
            for row in result['lines']:
                line_values.append(line_vals(row['name'], row['quantity'], row['price_unit']))
        elif untaxed is not None:
            name = (product.display_name if product else None) \
                or (result['ref'] and self.env._("Bill %(reference)s", reference=result['ref'])) \
                or (partner and self.env._("Bill of %(vendor)s", vendor=partner.name)) \
                or self.env._("Bill")
            line_values.append(line_vals(name, 1.0, untaxed))
        else:
            to_check.append(self.env._("Total"))

        with self.with_context(disable_onchange_name_predictive=['all'])._get_edi_creation() as move:
            if 'move_type' in values:
                move.move_type = values.pop('move_type')
            move.write(values)
            # the due date of the bill, unless the vendor has payment terms
            if result['invoice_date_due'] and not move.invoice_payment_term_id:
                move.invoice_date_due = result['invoice_date_due']
            if line_values:
                move.invoice_line_ids = [Command.create(vals) for vals in line_values]

        if total is not None and line_values and float_compare(
                self.amount_total, total, precision_rounding=self.currency_id.rounding) != 0:
            to_check.append(self.env._("Total"))
        elif result['total_guessed'] or (total is not None and not result['totals_consistent'] and not result['lines']):
            # one amount read, nothing to confirm it
            to_check.append(self.env._("Total"))

        to_check = list(dict.fromkeys(to_check))
        self.write({
            'om_ocr_state': 'to_check' if to_check else 'done',
            'om_ocr_to_check': ', '.join(to_check) or False,
            'om_ocr_text': text,
            'om_ocr_data': {
                'source': source,
                'found_by': found_by,
                'line_mode': line_mode,
                'date_order': date_order,
                'ambiguous_dates': result['ambiguous_dates'],
                'vat_numbers': [vat for vat in result['vat_numbers'] if vat not in own_vats],
                'ibans': [iban for iban in result['ibans'] if iban not in own_ibans],
                'email_domains': sorted({email.split('@')[-1] for email in result['emails']} - own_domains
                                        - PUBLIC_EMAIL_DOMAINS),
                'header_keys': self._om_ocr_header_keys(result)[:2],
                'read_total': total,
            },
        })
        self._om_ocr_message(found_by, source, to_check, line_mode)

    def _om_ocr_message(self, found_by, source, to_check, line_mode):
        how = {
            'vat': self.env._("its tax number"),
            'iban': self.env._("its bank account"),
            'learned': self.env._("what its earlier bills taught"),
            'email': self.env._("its email"),
            'name': self.env._("its name"),
        }
        parts = [self.env._("The bill was read from its text.") if source == 'text'
                 else self.env._("The bill was read from its scan, by OCR.")]
        if found_by:
            parts.append(self.env._("The vendor was recognized by %(how)s.", how=how[found_by]))
        parts.append(self.env._("Its lines were read from its table.") if line_mode == 'lines'
                     else self.env._("It was booked on one line."))
        if to_check:
            parts.append(self.env._("To check: %(fields)s.", fields=', '.join(to_check)))
        self.message_post(body=Markup('<br/>').join(parts))

    # ------------------------------------------------------------------------------------------------------
    # reading on demand
    # ------------------------------------------------------------------------------------------------------

    def _om_ocr_attachments(self):
        self.ensure_one()
        attachments = self.message_main_attachment_id | self.attachment_ids.sorted('id', reverse=True)
        return attachments.filtered(
            lambda a: a.mimetype == 'application/pdf' or is_image(a.mimetype, a.name))

    def action_om_ocr_read(self):
        for move in self:
            if not move.is_purchase_document(include_receipts=True) or move.state != 'draft':
                raise UserError(self.env._("Only a draft vendor bill can be read."))
            if move.invoice_line_ids:
                raise UserError(self.env._("The bill already has lines: delete them to read it again."))
            attachment = move._om_ocr_attachments()[:1]
            if not attachment:
                raise UserError(self.env._("Attach the PDF or the image of the bill first."))
            file_data = self._to_files_data(attachment)[0]
            reason = move._om_ocr_decode(file_data)
            if reason:
                raise UserError(self.env._("The bill was not read: %(reason)s", reason=reason))
        return True

    # ------------------------------------------------------------------------------------------------------
    # learning
    # ------------------------------------------------------------------------------------------------------

    def _post(self, soft=True):
        posted = super()._post(soft)
        for move in posted.filtered(lambda m: m.om_ocr_text and m.is_purchase_document(include_receipts=True)):
            try:
                with self.env.cr.savepoint():
                    move._om_ocr_learn()
            except Exception:  # noqa: BLE001 learning must never stop a bill from being posted
                _logger.warning("Bill recognition could not learn from %s", move.display_name, exc_info=True)
        return posted

    def _om_ocr_learn(self):
        """ Learn from a read bill, as it was posted after the accountant's corrections: the labels the
        vendor prints before its fields, how it writes its dates, and the account and the taxes of its
        bills. """
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        if not partner:
            return
        text = self.om_ocr_text
        data = self.om_ocr_data or {}
        profile = self.env['om.bill.ocr.profile'].sudo()._for_partner(partner, self.company_id, create=True)
        values = {'bill_count': profile.bill_count + 1, 'last_learned': fields.Date.context_today(self)}

        lines = self.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
        if lines:
            values['account_id'] = Counter(lines.mapped('account_id')).most_common(1)[0][0].id
            tax_sets = Counter(tuple(sorted(line.tax_ids.ids)) for line in lines)
            values['tax_ids'] = [Command.set(list(tax_sets.most_common(1)[0][0]))]
            products = lines.mapped('product_id')
            values['product_id'] = products.id if len(lines) == 1 and len(products) == 1 else False
            if data.get('line_mode') == 'lines':
                values['line_mode'] = 'lines' if len(lines) > 1 else 'single'

        if self.ref and (label := bill_parser.label_before(text, [self.ref])):
            values['anchor_ref'] = label
        for field_name in ('invoice_date', 'invoice_date_due'):
            value = self[field_name]
            if not value:
                continue
            positions = bill_parser.date_positions(text, value)
            if positions:
                position, order = positions[0]
                if label := bill_parser.label_at(text, position):
                    values[f'anchor_{field_name}'] = label
                if field_name == 'invoice_date' and order and data.get('ambiguous_dates'):
                    values['date_order'] = order
        positions = bill_parser.amount_positions(text, self.amount_total, self.currency_id.decimal_places)
        if positions and (label := bill_parser.label_at(text, positions[-1])):
            values['anchor_amount_total'] = label

        profile.write(values)
        keys = data.get('vat_numbers', []) + data.get('ibans', []) + data.get('email_domains', [])
        if data.get('found_by') not in ('vat', 'iban'):
            # recognized by nothing it prints for sure: its letterhead will tell it next time
            keys += data.get('header_keys', [])
        profile._add_match_keys(keys)
