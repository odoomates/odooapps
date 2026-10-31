import base64
import csv
import io
import re
from datetime import date, datetime
from itertools import pairwise

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools.misc import get_lang

DATE_FORMATS = ('%Y-%m-%d', '%d/%m/%Y', '%d.%m.%Y', '%d-%m-%Y')
MAX_ERRORS = 10


def parse_amount(value):
    """ The number in a cell: 1234.56, 1,234.56, 1.234,56, 1234,56 or 1 234,56.

    :raise ValueError: when it is not a number
    """
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r'[\s\u00a0\u202f]', '', str(value or ''))
    if not text:
        return 0.0
    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')
        else:
            text = text.replace(',', '')
    elif ',' in text:
        # one comma followed by one or two digits is a decimal comma, any other is a thousands separator
        text = text.replace(',', '.') if re.fullmatch(r'-?\d*,\d{1,2}', text) else text.replace(',', '')
    return float(text)


class AccountLoanImport(models.TransientModel):
    _name = 'account.loan.import'
    _description = 'Import a Loan Schedule'

    loan_id = fields.Many2one('account.loan', string='Loan', required=True)
    company_id = fields.Many2one(related='loan_id.company_id')
    currency_id = fields.Many2one(related='loan_id.currency_id')
    file = fields.Binary(string='File', required=True, help="A CSV or XLSX file, one row per instalment.")
    filename = fields.Char(string='File Name')
    columns = fields.Selection(
        [('principal', 'Date, Principal, Interest'), ('instalment', 'Date, Instalment, Interest')],
        string='Columns', required=True, default='principal',
        help="The three first columns of the file. A first row of titles is skipped.")
    principal_to_import = fields.Monetary(
        string='Principal to Schedule', compute='_compute_principal_to_import',
        help="The principal the imported lines must repay: the principal of the loan less the paid instalments "
             "and the early repayments.")

    @api.depends('loan_id')
    def _compute_principal_to_import(self):
        for wizard in self:
            wizard.principal_to_import = wizard._principal_to_import() if wizard.loan_id else 0.0

    def _principal_to_import(self):
        loan = self.loan_id
        paid = loan.line_ids.filtered(lambda line: line.state == 'posted')
        repaid = loan.operation_ids.filtered(lambda op: op.state == 'posted' and op.operation_type == 'repayment')
        return loan.currency_id.round(loan.principal - sum(paid.mapped('principal')) - sum(repaid.mapped('amount')))

    # ------------------------------------------------------------
    # Reading the file
    # ------------------------------------------------------------

    def _read_rows(self):
        """ The rows of the file, as lists of cells (strings, numbers or dates). """
        self.ensure_one()
        content = base64.b64decode(self.file or b'')
        if not content:
            raise UserError(self.env._('The file is empty.'))
        if (self.filename or '').lower().endswith('.xlsx') or content[:2] == b'PK':
            return self._read_xlsx(content)
        return self._read_csv(content)

    def _read_xlsx(self, content):
        import openpyxl  # only needed for this format

        try:
            book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as error:  # any unreadable file
            raise UserError(self.env._('The file is not a readable XLSX file: %s', error)) from error
        sheet = book.worksheets[0]
        return [['' if cell is None else cell for cell in row] for row in sheet.iter_rows(values_only=True)]

    def _read_csv(self, content):
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = content.decode('latin-1')
        # a semicolon or a tab in the first line separates the columns, the commas being decimal ones
        first = next((line for line in text.splitlines() if line.strip()), '')
        delimiter = next((char for char in (';', '\t') if char in first), ',')
        return list(csv.reader(io.StringIO(text), delimiter=delimiter))

    def _parse_date(self, value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value or '').strip()
        for date_format in (*DATE_FORMATS, get_lang(self.env).date_format):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        raise ValueError(text)

    def _parse_rows(self, rows):
        """ The instalments of the file, checked one by one.

        :return: list of dicts with date, principal, interest
        :raise UserError: listing the rows in error
        """
        currency = self.currency_id
        values, errors = [], []
        for number, row in enumerate(rows, start=1):
            cells = list(row) + [''] * 3
            if not any(str(cell).strip() for cell in cells[:3]):
                continue
            try:
                day = self._parse_date(cells[0])
            except ValueError:
                if number == 1:
                    continue  # the titles
                errors.append(self.env._('Row %(row)s: %(value)s is not a date.', row=number, value=cells[0]))
                continue
            try:
                first, interest = parse_amount(cells[1]), parse_amount(cells[2])
            except ValueError:
                errors.append(self.env._('Row %s: the amounts are not numbers.', number))
                continue
            interest = currency.round(interest)
            principal = currency.round(first - interest if self.columns == 'instalment' else first)
            if currency.compare_amounts(interest, 0.0) < 0:
                errors.append(self.env._('Row %s: the interest is negative.', number))
            if currency.compare_amounts(principal, 0.0) < 0:
                errors.append(self.env._(
                    'Row %s: the principal is negative (an instalment lower than its interest).', number))
            values.append({'row': number, 'date': day, 'principal': principal, 'interest': interest})
        if errors:
            raise UserError('\n'.join(errors[:MAX_ERRORS]))
        return values

    def _check_schedule(self, values):
        """ Check the imported instalments against the loan: dates increasing and after the paid ones, the
        principal adding up to what is left to repay. """
        loan = self.loan_id
        currency = self.currency_id
        if not values:
            raise UserError(self.env._('The file has no instalment.'))
        errors = []
        paid = loan.line_ids.filtered(lambda line: line.state == 'posted')
        operations = loan.operation_ids.filtered(lambda op: op.state == 'posted')
        after = max([loan.date_start, *paid.mapped('date'), *operations.mapped('date')])
        if values[0]['date'] <= after:
            errors.append(self.env._(
                'Row %(row)s: the first instalment must be due after %(date)s.', row=values[0]['row'], date=after))
        for previous, vals in pairwise(values):
            if vals['date'] <= previous['date']:
                errors.append(self.env._(
                    'Row %(row)s: the due dates must increase, %(date)s is not after %(previous)s.',
                    row=vals['row'], date=vals['date'], previous=previous['date']))
        total = currency.round(sum(vals['principal'] for vals in values))
        expected = self._principal_to_import()
        if currency.compare_amounts(total, expected):
            errors.append(self.env._(
                'The principal of the file adds up to %(total)s: the loan has %(expected)s to repay.',
                total=currency.format(total), expected=currency.format(expected)))
        if errors:
            raise UserError('\n'.join(errors[:MAX_ERRORS]))

    # ------------------------------------------------------------
    # Import
    # ------------------------------------------------------------

    def action_import(self):
        """ Replace the unpaid lines of the loan by the instalments of the file. """
        self.ensure_one()
        loan = self.loan_id
        if loan.state not in ('draft', 'running') or loan.schedule_method != 'imported':
            raise UserError(self.env._('Choose the Imported schedule method on a draft or running loan first.'))
        values = self._parse_rows(self._read_rows())
        self._check_schedule(values)
        kept = loan.line_ids.filtered(lambda line: line.state == 'posted')
        commands = [Command.unlink(line.id) for line in loan.line_ids - kept]
        commands += [
            Command.create({
                'sequence': number,
                'date': vals['date'],
                'principal': vals['principal'],
                'interest': vals['interest'],
                'rate': loan._rate_at(vals['date']),
            })
            for number, vals in enumerate(values, start=len(kept) + 1)
        ]
        loan_vals = {'payment_count': len(kept) + len(values)}
        if not kept and not loan._has_entries():
            loan_vals['date_first_payment'] = values[0]['date']
        loan.with_context(loan_no_regenerate=True).write(loan_vals)
        loan.with_context(loan_schedule_update=True).line_ids = commands
        loan._chain_balances()
        loan.message_post(body=self.env._(
            'Schedule of %(count)s instalments imported from %(file)s.',
            count=len(values), file=self.filename or self.env._('a file')))
        return {'type': 'ir.actions.act_window_close'}
