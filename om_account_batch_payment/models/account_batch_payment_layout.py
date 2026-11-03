import csv
import io

import xlsxwriter

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

DATE_FORMATS = [
    ('%d/%m/%Y', 'DD/MM/YYYY'),
    ('%m/%d/%Y', 'MM/DD/YYYY'),
    ('%Y-%m-%d', 'YYYY-MM-DD'),
    ('%d-%m-%Y', 'DD-MM-YYYY'),
    ('%d.%m.%Y', 'DD.MM.YYYY'),
    ('%d%m%Y', 'DDMMYYYY'),
    ('%Y%m%d', 'YYYYMMDD'),
    ('%d-%b-%Y', 'DD-Mon-YYYY'),
]
VALUES = [
    ('line_number', 'Line Number'),
    ('payment_name', 'Payment Number'),
    ('batch_name', 'Batch Reference'),
    ('date', 'Payment Date'),
    ('partner_name', 'Partner Name'),
    ('partner_ref', 'Partner Reference'),
    ('partner_vat', 'Partner Tax ID'),
    ('partner_email', 'Partner Email'),
    ('partner_phone', 'Partner Phone'),
    ('partner_city', 'Partner City'),
    ('partner_country', 'Partner Country Code'),
    ('holder_name', 'Account Holder Name'),
    ('account_number', 'Account Number'),
    ('bic', 'BIC / SWIFT / IFSC'),
    ('bank_name', 'Bank Name'),
    ('amount', 'Amount'),
    ('currency', 'Currency Code'),
    ('memo', 'Memo'),
    ('company_account', 'Account Number of the Company'),
    ('text', 'Fixed Text'),
]
# the values only the bank account of the partner gives
BANK_VALUES = {'holder_name', 'account_number', 'bic', 'bank_name'}


class AccountBatchPaymentLayout(models.Model):
    _name = 'account.batch.payment.layout'
    _description = 'Bank File Layout'
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', help="Leave empty to share the layout.")
    file_type = fields.Selection([('csv', 'CSV / Text'), ('xlsx', 'Excel')], required=True, default='csv')
    delimiter = fields.Selection(
        [(',', 'Comma'), (';', 'Semicolon'), ('\t', 'Tab'), ('|', 'Pipe')], required=True, default=',')
    quoting = fields.Selection(
        [('minimal', 'When Needed'), ('all', 'Every Value')], string='Quotes', required=True, default='minimal')
    encoding = fields.Selection(
        [('utf-8', 'UTF-8'), ('utf-8-sig', 'UTF-8 with BOM (Excel)'), ('cp1252', 'Windows-1252')],
        required=True, default='utf-8')
    include_header = fields.Boolean(string='Header Row', default=True, help="Writes the column titles first.")
    date_format = fields.Selection(DATE_FORMATS, required=True, default='%d/%m/%Y')
    decimal_separator = fields.Selection([('.', 'Point'), (',', 'Comma')], required=True, default='.')
    amount_in_cents = fields.Boolean(
        string='Amount in Cents', help="Writes 1234.50 as 123450, as some banks expect.")
    line_ids = fields.One2many('account.batch.payment.layout.line', 'layout_id', string='Columns', copy=True)
    preview = fields.Text(compute='_compute_preview')

    @api.depends('line_ids', 'line_ids.value', 'line_ids.title', 'line_ids.text', 'line_ids.max_length',
                 'line_ids.uppercase', 'delimiter', 'include_header', 'date_format', 'decimal_separator',
                 'amount_in_cents')
    def _compute_preview(self):
        sample = {
            'line_number': 1, 'payment_name': 'PBNK1/2026/00042', 'batch_name': 'BATCH/OUT/2026/0007',
            'date': fields.Date.context_today(self), 'partner_name': 'Sample Supplier Ltd', 'partner_ref': 'S042',
            'partner_vat': 'GB123456789', 'partner_email': 'accounts@supplier.example',
            'partner_phone': '+44 20 7946 0000', 'partner_city': 'London', 'partner_country': 'GB',
            'holder_name': 'Sample Supplier Ltd', 'account_number': 'GB29NWBK60161331926819',
            'bic': 'NWBKGB2L', 'bank_name': 'Sample Bank', 'amount': 12345.5, 'currency': 'GBP',
            'memo': 'BILL/2026/0042', 'company_account': 'GB33BUKB20201555555555',
        }
        currency = self.env.company.currency_id
        for layout in self:
            rows = [layout._format_row(sample, currency, as_text=True)]
            if layout.include_header:
                rows.insert(0, [line.title or '' for line in layout.line_ids])
            separator = '\\t' if layout.delimiter == '\t' else layout.delimiter
            layout.preview = '\n'.join(separator.join(str(value) for value in row) for row in rows)

    # -------------------------------------------------------------------------
    # Values
    # -------------------------------------------------------------------------

    def _payment_values(self, payment, line_number):
        bank = payment.partner_bank_id
        partner = payment.partner_id
        return {
            'line_number': line_number,
            'payment_name': payment.name or '',
            'batch_name': payment.batch_payment_id.name or '',
            'date': payment.date,
            'partner_name': partner.name or '',
            'partner_ref': partner.ref or '',
            'partner_vat': partner.vat or '',
            'partner_email': partner.email or '',
            'partner_phone': partner.phone or '',
            'partner_city': partner.city or '',
            'partner_country': partner.country_id.code or '',
            'holder_name': bank.acc_holder_name or partner.name or '',
            'account_number': bank.acc_number or '',
            'bic': bank.bank_bic or '',
            'bank_name': bank.bank_name or '',
            'amount': payment.amount,
            'currency': payment.currency_id.name,
            'memo': payment.memo or payment.payment_reference or '',
            'company_account': payment.journal_id.bank_account_id.acc_number or '',
        }

    def _format_amount(self, amount, currency, as_text):
        if self.amount_in_cents:
            cents = round(amount * 10 ** currency.decimal_places)
            return str(cents) if as_text else cents
        if not as_text:
            return currency.round(amount)
        text = '%.*f' % (currency.decimal_places, amount)
        return text.replace('.', ',') if self.decimal_separator == ',' else text

    def _format_row(self, values, currency, as_text):
        self.ensure_one()
        row = []
        for line in self.line_ids:
            if line.value == 'text':
                value = line.text or ''
            elif line.value == 'amount':
                value = self._format_amount(values['amount'], currency, as_text)
            elif line.value == 'date':
                value = values['date'].strftime(self.date_format) if values['date'] else ''
            else:
                value = values.get(line.value, '')
            if isinstance(value, str):
                if line.uppercase:
                    value = value.upper()
                if line.max_length:
                    value = value[:line.max_length]
            row.append(value)
        return row

    def _check_payments(self, payments):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('The bank file layout %s has no column.', self.name))
        if BANK_VALUES.intersection(self.line_ids.mapped('value')):
            if missing := payments.filtered(lambda payment: not payment.partner_bank_id):
                raise UserError(_(
                    'The bank file needs the bank account of the partner, missing on: %s',
                    ', '.join(missing.mapped('display_name'))))

    # -------------------------------------------------------------------------
    # File
    # -------------------------------------------------------------------------

    def _generate_file(self, batch):
        """ :return: (content as bytes, file name) """
        self.ensure_one()
        payments = batch._om_active_payments().sorted(lambda payment: (payment.partner_id.name or '', payment.id))
        currency = batch.currency_id
        header = [line.title or '' for line in self.line_ids] if self.include_header else None
        filename = '%s.%s' % (batch.name.replace('/', '_'), self.file_type)
        if self.file_type == 'xlsx':
            rows = [self._format_row(self._payment_values(payment, number), currency, as_text=False)
                    for number, payment in enumerate(payments, start=1)]
            return self._write_xlsx(header, rows, currency), filename
        rows = [self._format_row(self._payment_values(payment, number), currency, as_text=True)
                for number, payment in enumerate(payments, start=1)]
        return self._write_csv(header, rows), filename

    def _write_csv(self, header, rows):
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=self.delimiter, lineterminator='\r\n',
                            quoting=csv.QUOTE_ALL if self.quoting == 'all' else csv.QUOTE_MINIMAL)
        if header:
            writer.writerow(header)
        writer.writerows(rows)
        return buffer.getvalue().encode(self.encoding, errors='replace')

    def _write_xlsx(self, header, rows, currency):
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
        sheet = workbook.add_worksheet('Payments')
        bold = workbook.add_format({'bold': True})
        number = workbook.add_format({'num_format': '0' if self.amount_in_cents
                                      else '0.' + '0' * currency.decimal_places})
        amount_columns = {index for index, line in enumerate(self.line_ids) if line.value == 'amount'}
        row_index = 0
        if header:
            sheet.write_row(0, 0, header, bold)
            row_index = 1
        for row in rows:
            for column, value in enumerate(row):
                if column in amount_columns and not isinstance(value, str):
                    sheet.write_number(row_index, column, value, number)
                else:
                    sheet.write_string(row_index, column, str(value))
            row_index += 1
        for column, line in enumerate(self.line_ids):
            sheet.set_column(column, column, max(len(line.title or ''), 12) + 2)
        workbook.close()
        return buffer.getvalue()


class AccountBatchPaymentLayoutLine(models.Model):
    _name = 'account.batch.payment.layout.line'
    _description = 'Column of a Bank File Layout'
    _order = 'sequence, id'

    layout_id = fields.Many2one('account.batch.payment.layout', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    title = fields.Char(string='Column Title', translate=True)
    value = fields.Selection(VALUES, required=True, default='partner_name')
    text = fields.Char(string='Fixed Text')
    max_length = fields.Integer(string='Maximum Length', help="Cuts longer values; 0 for no limit.")
    uppercase = fields.Boolean(string='Capitals')

    @api.constrains('max_length')
    def _check_max_length(self):
        if any(line.max_length < 0 for line in self):
            raise ValidationError(_('The maximum length cannot be negative.'))
