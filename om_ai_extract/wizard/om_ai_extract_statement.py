from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import float_compare, float_is_zero

STATEMENT_PROPERTIES = {
    'bank_name': {'type': ['string', 'null']},
    'account_number': {'type': ['string', 'null'], 'description': 'Account number or IBAN of the statement'},
    'statement_number': {'type': ['string', 'null']},
    'currency': {'type': ['string', 'null'], 'description': 'ISO code, e.g. EUR'},
    'start_date': {'type': ['string', 'null'], 'format': 'date'},
    'end_date': {'type': ['string', 'null'], 'format': 'date'},
    'opening_balance': {'type': ['number', 'null']},
    'closing_balance': {'type': ['number', 'null']},
    'transactions': {
        'type': 'array',
        'items': {
            'type': 'object',
            'properties': {
                'date': {'type': ['string', 'null'], 'format': 'date'},
                'description': {'type': ['string', 'null'], 'description': 'Label of the transaction'},
                'partner_name': {'type': ['string', 'null'], 'description': 'Payer or payee if printed'},
                'reference': {'type': ['string', 'null']},
                'amount': {'type': ['number', 'null'],
                           'description': 'Positive for money received, negative for money paid'},
            },
            'required': ['date', 'description', 'partner_name', 'reference', 'amount'],
            'additionalProperties': False,
        },
    },
}
INSTRUCTIONS = """Read this bank statement. List every transaction in the order printed, with a positive amount for
money received (credit) and a negative amount for money paid (debit). Give the opening and closing balances as
printed. Do not add totals or balance lines as transactions."""


class OmAiExtractStatement(models.TransientModel):
    _name = 'om.ai.extract.statement'
    _description = 'Read a Bank Statement with AI'

    state = fields.Selection([('upload', 'Upload'), ('review', 'Review')], default='upload', required=True)
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True, domain=[('type', 'in', ('bank', 'cash', 'credit'))],
        default=lambda self: self._default_journal())
    company_id = fields.Many2one(related='journal_id.company_id')
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id')
    file = fields.Binary(string='Statement File', required=True, attachment=False)
    filename = fields.Char()
    name = fields.Char(string='Reference')
    date = fields.Date(string='Statement Date')
    balance_start = fields.Monetary(string='Opening Balance', currency_field='currency_id')
    balance_end_real = fields.Monetary(string='Closing Balance', currency_field='currency_id')
    balance_end = fields.Monetary(string='Computed Closing Balance', currency_field='currency_id',
                                  compute='_compute_balance_end')
    line_ids = fields.One2many('om.ai.extract.statement.line', 'wizard_id', string='Transactions')
    confidence = fields.Float(string='AI Confidence', readonly=True)
    checks = fields.Text(string='To Check', readonly=True)
    read_currency = fields.Char(string='Currency Read', readonly=True)
    read_account = fields.Char(string='Account Read', readonly=True)

    @api.model
    def _default_journal(self):
        journal_id = self.env.context.get('default_journal_id') or (
            self.env.context.get('active_model') == 'account.journal' and self.env.context.get('active_id'))
        if journal_id:
            return self.env['account.journal'].browse(journal_id)
        return self.env['account.journal'].search([
            *self.env['account.journal']._check_company_domain(self.env.company), ('type', '=', 'bank')], limit=1)

    @api.depends('journal_id')
    def _compute_currency_id(self):
        for wizard in self:
            wizard.currency_id = wizard.journal_id.currency_id or wizard.journal_id.company_id.currency_id

    @api.depends('balance_start', 'line_ids.amount')
    def _compute_balance_end(self):
        for wizard in self:
            wizard.balance_end = wizard.balance_start + sum(wizard.line_ids.mapped('amount'))

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'name': self.env._('Read a Bank Statement with AI'),
        }

    def _guess_partner(self, name):
        if not name or len(name) < 3:
            return self.env['res.partner']
        Partner = self.env['res.partner']
        domain = Partner._check_company_domain(self.company_id)
        partners = Partner.search([*domain, ('name', '=ilike', name)], limit=2) \
            or Partner.search([*domain, ('name', 'ilike', name)], limit=2)
        return partners.commercial_partner_id if len(partners.commercial_partner_id) == 1 else Partner

    def action_read(self):
        self.ensure_one()
        Extract = self.env['om.ai.extract']
        raw = bytes(self.file) if self.file else b''
        mimetype = 'application/pdf' if Extract._is_pdf(None, self.filename, raw) else (
            'image/png' if raw[:4] == b'\x89PNG' else 'image/jpeg' if raw[:2] == b'\xff\xd8' else None)
        schema = Extract._schema(STATEMENT_PROPERTIES, required=list(STATEMENT_PROPERTIES))
        data, problems, _payload = Extract._extract(raw, mimetype, self.filename, schema, instructions=INSTRUCTIONS)
        checks = list(data['flags']) + problems
        lines = []
        for index, item in enumerate(data.get('transactions') or [], start=1):
            amount = item.get('amount')
            flag = []
            if amount is None or float_is_zero(amount, precision_rounding=self.currency_id.rounding):
                flag.append(self.env._('no amount'))
            if not item.get('date'):
                flag.append(self.env._('no date'))
            partner = self._guess_partner(item.get('partner_name'))
            lines.append(Command.create({
                'sequence': index,
                'date': item.get('date') or data.get('end_date') or fields.Date.context_today(self),
                'payment_ref': item.get('description') or item.get('reference') or '/',
                'partner_name': item.get('partner_name'),
                'partner_id': partner.id,
                'ref': item.get('reference'),
                'amount': amount or 0.0,
                'flag': ', '.join(flag) or False,
            }))
        currency = data.get('currency')
        if currency and currency.upper() != self.currency_id.name:
            checks.append(self.env._('The statement is in %(read)s, the journal in %(journal)s.',
                                     read=currency, journal=self.currency_id.name))
        account = data.get('account_number')
        journal_account = self.journal_id.bank_account_id.sanitized_account_number
        if account and journal_account and ''.join(account.split()).upper()[-6:] != journal_account.upper()[-6:]:
            checks.append(self.env._('The account number read (%s) is not the one of the journal.', account))
        if not lines:
            checks.append(self.env._('No transaction was read.'))
        self.line_ids = [Command.clear()] + lines
        self.write({
            'state': 'review',
            'name': data.get('statement_number') or self.filename,
            'date': data.get('end_date') or fields.Date.context_today(self),
            'balance_start': data.get('opening_balance') or 0.0,
            'balance_end_real': data.get('closing_balance') or 0.0,
            'confidence': data.get('confidence') or 0.0,
            'read_currency': currency,
            'read_account': account,
        })
        if data.get('closing_balance') is not None and float_compare(
                self.balance_end, self.balance_end_real, precision_rounding=self.currency_id.rounding):
            checks.append(self.env._('Opening balance plus transactions (%(computed)s) is not the closing balance '
                                     'read (%(read)s).', computed=self.balance_end, read=self.balance_end_real))
        if data.get('confidence') is not None and data['confidence'] < 0.7:
            checks.append(self.env._('The AI is not sure of this reading.'))
        self.checks = '\n'.join(dict.fromkeys(checks)) or False
        return self._reopen()

    def action_back(self):
        self.write({'state': 'upload', 'line_ids': [Command.clear()], 'checks': False})
        return self._reopen()

    def action_create(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(self.env._('There is no transaction to create.'))
        if any(not line.date for line in self.line_ids):
            raise UserError(self.env._('Every transaction needs a date.'))
        statement = self.env['account.bank.statement'].create({
            'name': self.name or self.filename,
            'date': self.date,
            'journal_id': self.journal_id.id,
            'balance_start': self.balance_start,
            'balance_end_real': self.balance_end_real,
            'line_ids': [Command.create({
                'date': line.date,
                'payment_ref': line.payment_ref,
                'partner_id': line.partner_id.id,
                'partner_name': line.partner_name if not line.partner_id else False,
                'amount': line.amount,
                'journal_id': self.journal_id.id,
                'transaction_details': {'reference': line.ref} if line.ref else False,
            }) for line in self.line_ids.sorted(lambda l: (l.date, l.sequence))],
        })
        attachment = self.env['ir.attachment'].create({
            'name': self.filename or 'statement',
            'raw': bytes(self.file),
            'res_model': 'account.bank.statement',
            'res_id': statement.id,
        })
        statement.attachment_ids = [Command.link(attachment.id)]
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.bank.statement.line',
            'name': self.env._('Transactions Read by AI'),
            'view_mode': 'list,form',
            'domain': [('statement_id', '=', statement.id)],
            'context': {'default_journal_id': self.journal_id.id},
        }


class OmAiExtractStatementLine(models.TransientModel):
    _name = 'om.ai.extract.statement.line'
    _description = 'Transaction Read by AI'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('om.ai.extract.statement', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    sequence = fields.Integer(default=10)
    date = fields.Date()
    payment_ref = fields.Char(string='Label')
    partner_name = fields.Char(string='Name Read')
    partner_id = fields.Many2one('res.partner', string='Partner')
    ref = fields.Char(string='Reference')
    amount = fields.Monetary(currency_field='currency_id')
    flag = fields.Char(string='To Check')
