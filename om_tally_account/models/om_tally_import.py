import logging
import re
from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

_logger = logging.getLogger(__name__)

GST_HEADS = [
    ('integrated tax', 'IGST'), ('igst', 'IGST'), ('central tax', 'CGST'), ('cgst', 'CGST'),
    ('state tax', 'SGST'), ('sgst', 'SGST'), ('ut tax', 'UTGST'), ('utgst', 'UTGST'), ('cess', 'CESS'),
    ('vat', 'VAT'),
]
SALE_WORDS = ('output', 'sale', 'payable', 'collected')
PURCHASE_WORDS = ('input', 'purchase', 'receivable', 'itc', 'paid')
# first codes of the new accounts when the chart has no account of that type
DEFAULT_CODES = {
    'asset_receivable': '121100', 'asset_cash': '101500', 'asset_current': '110100', 'asset_non_current': '160100',
    'asset_prepayments': '140100', 'asset_fixed': '150100', 'liability_payable': '211100',
    'liability_credit_card': '218100', 'liability_current': '230100', 'liability_non_current': '250100',
    'equity': '301100', 'equity_unaffected': '999900', 'income': '400100', 'income_other': '420100',
    'expense': '600100', 'expense_other': '640100', 'expense_depreciation': '660100',
    'expense_direct_cost': '500100', 'off_balance': '900100',
}
INVOICE_TYPES = {
    ('Sales', 'receivable'): 'out_invoice', ('Credit Note', 'receivable'): 'out_refund',
    ('Purchase', 'payable'): 'in_invoice', ('Debit Note', 'payable'): 'in_refund',
}
GST_TREATMENTS = {
    'regular': 'regular', 'composition': 'composition', 'unregistered': 'unregistered', 'consumer': 'consumer',
    'overseas': 'overseas', 'sez': 'special_economic_zone', 'special economic zone': 'special_economic_zone',
    'deemed export': 'deemed_export', 'uin holders': 'uin_holders',
}


def _norm(text):
    return ''.join(char for char in (text or '').lower() if char.isalnum())


def _digits(text):
    return re.sub(r'\D', '', text or '')


class OmTallyImport(models.Model):
    _inherit = 'om.tally.import'

    state = fields.Selection(selection_add=[
        ('mapped', 'Map'),
        ('checked', 'Check'),
        ('posting', 'Post'),
        ('done', 'Done'),
    ], ondelete={'mapped': 'set default', 'checked': 'set default', 'posting': 'set default',
                 'done': 'set default'})
    scope = fields.Selection([
        ('opening', 'Opening Balances'),
        ('history', 'Full History'),
    ], string='Import', default='opening', required=True, tracking=True,
        help="Opening balances: one opening entry as on the cut-over date, with the open bills. Full history: "
             "the opening entry at the first date, then every voucher until the last date.")
    cutover_date = fields.Date(string='Cut-over Date', tracking=True,
                               help="Odoo starts on this day: the opening entry is dated the day before. For the "
                                    "full history, the first day of the vouchers to import.")
    history_date_to = fields.Date(string='Import Vouchers Until', help="Empty: all the vouchers read.")
    history_method = fields.Selection([
        ('period', 'Split by Period'),
        ('background', 'Read in the Background'),
    ], string='How', default='period', required=True,
        help="Split by period: read and import one financial year (or any period) at a time; each run adds to the "
             "previous ones. Read in the background: Tally is read by a background job, one file or one month at a "
             "time, then everything is imported.")
    read_background = fields.Boolean(compute='_compute_read_background', store=True, readonly=False)
    current_period_done = fields.Boolean(compute='_compute_current_period_done')
    history_mode = fields.Selection([
        ('exact', 'Exact Journal Entries'),
        ('documents', 'Invoices, Bills and Payments'),
    ], string='Vouchers As', default='exact', required=True,
        help="Exact journal entries: each voucher becomes one entry with the lines of Tally, always balanced. "
             "Invoices, bills and payments: Sales and Purchase vouchers become invoices and bills, notes become "
             "refunds, receipts and payments are posted in the bank or cash journal and reconciled with the bills "
             "named in Tally.")
    opening_journal_id = fields.Many2one('account.journal', string='Opening Journal',
                                         domain="[('company_id', '=', company_id), ('type', '=', 'general')]")
    import_journal_id = fields.Many2one('account.journal', string='Journal of the Vouchers',
                                        domain="[('company_id', '=', company_id)]",
                                        help="The journal of the vouchers whose voucher type has no journal.")
    difference_account_id = fields.Many2one('account.account', string='Opening Difference Account',
                                            domain="[('company_ids', 'in', company_id)]",
                                            help="Takes the difference in opening balances of Tally (and the "
                                                 "Stock-in-Hand ledger when it is left out).")
    suspense_account_id = fields.Many2one('account.account', string='Suspense Account',
                                          domain="[('company_ids', 'in', company_id)]",
                                          help="Takes the amounts of the skipped ledgers and of unbalanced "
                                               "vouchers when you accept the differences.")
    accept_difference = fields.Boolean(string='Accept the Differences',
                                       help="Post even though the check shows differences: they go to the suspense "
                                            "account.")
    fallback_partner_id = fields.Many2one('res.partner', string='Partner of the Skipped Parties')
    exclude_stock_in_hand = fields.Boolean(
        string='Leave Stock-in-Hand Out',
        help="Leave the Stock-in-Hand ledgers out of the opening entry: their amount goes to the opening "
             "difference account. By default they stay in, on their account.")
    opening_move_id = fields.Many2one('account.move', string='Opening Entry', readonly=True, copy=False)
    check_line_ids = fields.One2many('om.tally.check.line', 'import_id', string='Trial Balance Check')
    check_difference = fields.Monetary(string='Difference to Explain', compute='_compute_check_difference',
                                       help="The differences between Tally and what Odoo will hold, not explained "
                                            "by the options chosen.")
    check_date = fields.Datetime(string='Checked On', readonly=True, copy=False)
    post_batch_size = fields.Integer(string='Vouchers per Batch', default=200)
    post_total = fields.Integer(string='Vouchers to Import', compute='_compute_post_progress')
    post_done = fields.Integer(string='Vouchers Imported', compute='_compute_post_progress')
    post_error = fields.Integer(string='Vouchers in Error', compute='_compute_post_progress')
    post_progress = fields.Float(string='Progress', compute='_compute_post_progress')
    move_count = fields.Integer(string='Entries', compute='_compute_post_progress')
    cost_centre_ids = fields.One2many('om.tally.cost.centre', 'import_id', string='Cost Centres')
    voucher_type_ids = fields.One2many('om.tally.voucher.type', 'import_id', string='Voucher Types')
    account_ledger_ids = fields.One2many('om.tally.ledger', 'import_id', string='Chart',
                                         domain=[('role', 'not in', ('receivable', 'payable'))])
    party_ledger_ids = fields.One2many('om.tally.ledger', 'import_id', string='Party Ledgers',
                                       domain=[('role', 'in', ('receivable', 'payable'))])
    unmatched_party_count = fields.Integer(compute='_compute_unmatched_party_count')

    # ------------------------------------------------------------------------------------------------------------
    # computes

    @api.depends('scope', 'history_method')
    def _compute_read_background(self):
        for record in self:
            record.read_background = record.scope == 'history' and record.history_method == 'background'

    @api.depends('period_ids.state', 'voucher_date_to')
    def _compute_current_period_done(self):
        for record in self:
            record.current_period_done = bool(record.period_ids.filtered(
                lambda p: p.state == 'imported' and p.date_to == record.voucher_date_to))

    @api.depends('check_line_ids.difference', 'check_line_ids.is_explained')
    def _compute_check_difference(self):
        for record in self:
            record.check_difference = sum(abs(line.difference) for line in record.check_line_ids
                                          if not line.is_explained)

    def _compute_post_progress(self):
        for record in self:
            vouchers = record.voucher_ids
            in_scope = vouchers.filtered(lambda v: v.state in ('staged', 'posted', 'error') and v.is_accounting
                                         and record._om_tally_in_scope(v))
            record.post_total = len(in_scope)
            record.post_done = len(in_scope.filtered(lambda v: v.state == 'posted'))
            record.post_error = len(in_scope.filtered(lambda v: v.state == 'error'))
            record.post_progress = 100.0 * record.post_done / record.post_total if record.post_total else (
                100.0 if record.state == 'done' else 0.0)
            record.move_count = len(vouchers.move_id) + (1 if record.opening_move_id else 0)

    def _compute_unmatched_party_count(self):
        for record in self:
            record.unmatched_party_count = len(record.party_ledger_ids.filtered(
                lambda l: l.partner_action == 'create'))

    # ------------------------------------------------------------------------------------------------------------
    # defaults of the company

    def _om_tally_default_partner_account(self, role):
        self.ensure_one()
        field = 'property_account_receivable_id' if role == 'receivable' else 'property_account_payable_id'
        partner = self.env['res.partner'].with_company(self.company_id)
        account = partner.new({})[field]
        if not account:
            account = self.env['account.account'].search([
                ('company_ids', 'in', self.company_id.id),
                ('account_type', '=', 'asset_receivable' if role == 'receivable' else 'liability_payable'),
                ('non_trade', '=', False)], limit=1)
        return account

    def _om_tally_accounts(self):
        return self.env['account.account'].with_company(self.company_id).search(
            [('company_ids', 'in', self.company_id.id)])

    def _om_tally_uses_codes(self, accounts):
        return sum(1 for account in accounts if account.code) * 2 > len(accounts)

    def _om_tally_new_code(self, account_type, accounts, used):
        """ A free code after the highest code of the type, if the chart uses codes. """
        if not self._om_tally_uses_codes(accounts):
            return False
        codes = sorted((account.code for account in accounts if account.account_type == account_type and account.code
                        and account.code.isdigit()), key=lambda code: (len(code), code))
        Account = self.env['account.account'].with_company(self.company_id)
        if codes:
            code = Account._search_new_account_code(codes[-1], cache=set(used) | {codes[-1]})
        else:
            code = Account._search_new_account_code(DEFAULT_CODES.get(account_type, '999000'), cache=set(used))
        used.add(code)
        return code

    def _om_tally_tax_direction(self, ledger):
        name = ledger.name.lower()
        if any(word in name for word in PURCHASE_WORDS):
            return 'purchase'
        if any(word in name for word in SALE_WORDS):
            return 'sale'
        return False

    def _om_tally_tax_head(self, ledger):
        text = f"{ledger.gst_duty_head or ''} {ledger.name}".lower()
        for word, head in GST_HEADS:
            if word in text:
                return head
        return ledger.tax_type or False

    def _om_tally_find_tax(self, ledger, direction=None, rate=None):
        """ The tax of Odoo a tax ledger stands for: same duty head (CGST, SGST, IGST in India), rate and use
        (sale or purchase); in the Gulf, the VAT tax of the same rate. """
        self.ensure_one()
        head = self._om_tally_tax_head(ledger)
        direction = direction or self._om_tally_tax_direction(ledger)
        rate = rate if rate is not None else ledger.tax_rate
        if not head or not direction or head in ('TDS', 'TCS'):
            return self.env['account.tax']
        Tax = self.env['account.tax'].with_company(self.company_id)
        if self.tally_country in ('ae', 'sa', 'bh') or head == 'VAT':
            return self._om_tally_find_vat(direction, rate or {'ae': 5.0, 'bh': 10.0, 'sa': 15.0}.get(
                self.tally_country, 0.0))
        domain = [('company_id', '=', self.company_id.id), ('amount_type', '=', 'percent'), ('name', 'ilike', head)]
        if rate:
            domain.append(('amount', '=', rate))
        candidates = Tax.search(domain)
        for tax in candidates:
            if tax.name and any(word in tax.name.upper() for word in ('RC', 'EXP', 'SEZ', 'IMP')) and \
                    'RC' not in ledger.name.upper():
                continue
            use = tax.type_tax_use
            if use == 'none':
                parent = Tax.search([('children_tax_ids', 'in', tax.id)], limit=1)
                use = parent.type_tax_use
            if use == direction and (rate or len(candidates.mapped('amount')) == 1):
                return tax
        return self.env['account.tax']

    def _om_tally_find_vat(self, direction, rate):
        """ The VAT tax of a rate (5% UAE, 15% Saudi Arabia, 10% Bahrain), for sales or purchases. """
        if not rate:
            return self.env['account.tax']
        taxes = self.env['account.tax'].with_company(self.company_id).search([
            ('company_id', '=', self.company_id.id), ('amount_type', '=', 'percent'), ('amount', '=', rate),
            ('type_tax_use', '=', direction)])
        excluded = ('RC', 'REVERSE', 'EXEMPT', 'IMPORT', 'EXPORT', 'DEEMED')
        taxes = taxes.filtered(lambda t: not any(word in (t.name or '').upper() for word in excluded))
        return taxes.sorted(lambda t: (0 if 'VAT' in (t.name or '').upper() else 1, t.sequence, t.id))[:1]

    def _om_tally_tax_account(self, tax):
        return tax.invoice_repartition_line_ids.filtered(lambda r: r.repartition_type == 'tax').account_id[:1]

    # ------------------------------------------------------------------------------------------------------------
    # proposing the mapping

    def action_analyze(self):
        res = super().action_analyze()
        for record in self:
            record._om_tally_account_defaults()
        return res

    def _om_tally_account_defaults(self):
        accounts = self._om_tally_accounts()
        if not self.cutover_date:
            self.cutover_date = self.books_from
        if not self.difference_account_id:
            self.difference_account_id = accounts.filtered(lambda a: a.account_type == 'equity_unaffected')[:1] or \
                accounts.filtered(lambda a: a.account_type == 'equity')[:1]
        if not self.suspense_account_id:
            self.suspense_account_id = accounts.filtered(
                lambda a: 'suspense' in (a.name or '').lower() and a.account_type == 'liability_current')[:1]

    def action_propose_mapping(self):
        for record in self:
            record._om_tally_propose_mapping()
            record._om_tally_log(self.env._("Mapping proposed for %s ledgers.", len(record.ledger_ids)), step='map')
        return True

    def _om_tally_propose_mapping(self):
        self.ensure_one()
        env, company = self.env, self.company_id
        Mapping = env['om.tally.mapping']
        accounts = self._om_tally_accounts()
        by_name = {}
        by_norm = defaultdict(list)
        for account in accounts:
            by_name.setdefault((account.name or '').lower(), account)
            by_norm[_norm(account.name)].append(account)
        used = set(accounts.mapped('code'))
        journals = env['account.journal'].search([('company_id', '=', company.id), ('type', 'in', ('bank', 'cash'))])
        unaffected = accounts.filtered(lambda a: a.account_type == 'equity_unaffected')[:1]
        self._om_tally_account_defaults()

        def same_class(account, account_type):
            return account.account_type.split('_')[0] == (account_type or '').split('_')[0]

        for ledger in self.ledger_ids.filtered(lambda l: l.role not in ('receivable', 'payable') and not l.is_applied):
            vals = {'account_id': False, 'account_action': 'create', 'match_note': False, 'new_account_code': False}
            account = Mapping._om_tally_find(company, 'ledger', ledger.guid, 'account.account')
            note = env._("Imported before") if account else False
            if not account and ledger.role == 'pl':
                account, note = unaffected, env._("Current year earnings")
            if ledger.role in ('bank', 'cash'):
                journal = Mapping._om_tally_find(company, 'journal', ledger.guid, 'account.journal')
                if not journal and ledger.bank_account_number:
                    number = _norm(ledger.bank_account_number)
                    journal = journals.filtered(lambda j: _norm(j.bank_account_number) == number)[:1]
                if not journal:
                    journal = journals.filtered(lambda j: _norm(j.name) == _norm(ledger.name))[:1]
                if not journal and ledger.role == 'cash':
                    cash = journals.filtered(lambda j: j.type == 'cash')
                    journal = cash if len(cash) == 1 else journal
                vals.update({'journal_id': journal.id, 'journal_action': 'link' if journal else 'create'})
                if journal:
                    account, note = journal.default_account_id, env._("Journal %s", journal.name)
            if not account and ledger.role == 'tax':
                tax = self._om_tally_find_tax(ledger)
                vals['tax_id'] = tax.id
                account = self._om_tally_tax_account(tax)
                note = account and env._("Tax %s", tax.name)
                if not account:
                    head, direction = self._om_tally_tax_head(ledger), self._om_tally_tax_direction(ledger)
                    if head and direction:
                        account = by_name.get(f"{head} {'payable' if direction == 'sale' else 'receivable'}".lower())
                        note = account and env._("Tax account")
                if direction := self._om_tally_tax_direction(ledger):
                    vals['account_type'] = 'asset_current' if direction == 'purchase' else 'liability_current'
            if not account and ledger.role == 'stock':
                account = next((acc for acc in accounts if acc.account_type == 'asset_current' and any(
                    word in (acc.name or '').lower() for word in ('stock valuation', 'inventory', 'stock in hand'))),
                    env['account.account'])
                note = account and env._("Stock account")
            if not account:
                exact = by_name.get(ledger.name.lower())
                if exact and same_class(exact, ledger.account_type):
                    account, note = exact, env._("Same name")
            if not account:
                similar = [acc for acc in by_norm.get(_norm(ledger.name), []) if acc.account_type == ledger.account_type]
                if similar:
                    account, note = similar[0], env._("Similar name")
            if account:
                vals.update({'account_id': account.id, 'account_action': 'link', 'match_note': note})
            else:
                account_type = vals.get('account_type') or ledger.account_type
                vals['new_account_code'] = self._om_tally_new_code(account_type, accounts, used)
            ledger.write(vals)
        self._om_tally_propose_partners()
        self._om_tally_propose_analytic()
        if not self.opening_journal_id or not self.import_journal_id:
            journals = self.env['account.journal'].search([('company_id', '=', company.id), ('type', '=', 'general')])
            self.opening_journal_id = self.opening_journal_id or journals.filtered(lambda j: j.code == 'TLYOP')[:1]
            self.import_journal_id = self.import_journal_id or journals.filtered(lambda j: j.code == 'TALLY')[:1]

    def _om_tally_propose_partners(self):
        env, company = self.env, self.company_id
        Partner = env['res.partner'].with_context(active_test=False)
        Mapping = env['om.tally.mapping']
        company_domain = [('company_id', 'in', (False, company.id))]
        defaults = {role: self._om_tally_default_partner_account(role) for role in ('receivable', 'payable')}
        for ledger in self.ledger_ids.filtered(lambda l: l.role in ('receivable', 'payable') and not l.is_applied):
            partner = Mapping._om_tally_find(company, 'party', ledger.guid, 'res.partner')
            note = partner and env._("Imported before")
            tax_number = ledger.gstin or ledger.vat_number
            if not partner and tax_number:
                partner = Partner.search(company_domain + [('vat', '=ilike', tax_number)], limit=1)
                note = partner and env._("GSTIN/VAT")
            if not partner:
                partner = Partner.search(company_domain + [('name', '=ilike', ledger.name), ('parent_id', '=', False)],
                                         limit=1)
                note = partner and env._("Name")
            if not partner:
                for number in (ledger.mobile, ledger.phone):
                    digits = _digits(number)
                    if len(digits) >= 8:
                        partner = Partner.search(company_domain + [('phone', 'ilike', digits[-4:])]).filtered(
                            lambda p: _digits(p.phone).endswith(digits[-8:]))[:1]
                        if partner:
                            note = env._("Phone")
                            break
            if not partner and ledger.email:
                partner = Partner.search(company_domain + [('email', '=ilike', ledger.email)], limit=1)
                note = partner and env._("Email")
            ledger.write({
                'partner_id': partner.id,
                'partner_action': 'link' if partner else 'create',
                'partner_match_note': note or False,
                'account_id': ledger.account_id.id or defaults[ledger.role].id,
                'account_action': 'link',
            })

    def _om_tally_propose_analytic(self):
        env = self.env
        Plan, Analytic = env['account.analytic.plan'].sudo(), env['account.analytic.account'].sudo()
        for category in env['om.tally.cost.category'].search([('import_id', '=', self.id)]):
            if not category.analytic_plan_id:
                category.analytic_plan_id = Plan.search([('name', '=ilike', category.name)], limit=1)
        for centre in self.cost_centre_ids:
            account = env['om.tally.mapping']._om_tally_find(self.company_id, 'cost_centre', centre.guid,
                                                              'account.analytic.account')
            if not account:
                domain = [('name', '=ilike', centre.name), ('company_id', 'in', (False, self.company_id.id))]
                if centre.category_id.analytic_plan_id:
                    domain.append(('plan_id', '=', centre.category_id.analytic_plan_id.id))
                account = Analytic.search(domain, limit=1)
            centre.write({'analytic_account_id': account.id, 'analytic_action': 'link' if account else 'create'})

    # bulk actions on the parties

    def action_parties_create_unmatched(self):
        self.party_ledger_ids.filtered(lambda l: not l.partner_id).write({'partner_action': 'create'})
        return True

    def action_parties_skip_unmatched(self):
        self.party_ledger_ids.filtered(lambda l: not l.partner_id).write({'partner_action': 'skip'})
        return True

    def action_parties_link_matched(self):
        self.party_ledger_ids.filtered(lambda l: l.partner_id).write({'partner_action': 'link'})
        return True

    # ------------------------------------------------------------------------------------------------------------
    # creating and linking the Odoo records

    def _om_tally_ensure_journals(self):
        Journal = self.env['account.journal']
        company = self.company_id
        for field, code, name in (('opening_journal_id', 'TLYOP', self.env._("Opening Balances (Tally)")),
                                  ('import_journal_id', 'TALLY', self.env._("Tally Vouchers"))):
            if not self[field]:
                journal = Journal.search([('company_id', '=', company.id), ('code', '=', code)], limit=1)
                self[field] = journal or Journal.create({'name': name, 'code': code, 'type': 'general',
                                                         'company_id': company.id})

    def _om_tally_journal_code(self, name):
        Journal = self.env['account.journal']
        base = (re.sub(r'[^A-Z0-9]', '', (name or '').upper()) or 'BNK')[:3]
        for index in range(1, 100):
            code = f'{base}{index}'[:5]
            if not Journal.search_count([('company_id', '=', self.company_id.id), ('code', '=', code)]):
                return code
        return False

    def _om_tally_partner_vals(self, ledger):
        env = self.env
        lines = [line.strip() for line in (ledger.address or '').splitlines() if line.strip()]
        country = env['res.country'].search([('name', '=ilike', ledger.country_name)], limit=1) \
            if ledger.country_name else self.company_id.country_id
        state = env['res.country.state'].search([('name', '=ilike', ledger.state_name),
                                                 ('country_id', '=', country.id)], limit=1) \
            if ledger.state_name and country else env['res.country.state']
        vals = {
            'name': ledger.name,
            'is_company': True,
            'street': lines[0] if lines else False,
            'street2': ', '.join(lines[1:-1]) if len(lines) > 2 else False,
            'city': lines[-1] if len(lines) > 1 else False,
            'zip': ledger.pincode or False,
            'country_id': country.id,
            'state_id': state.id,
            'email': ledger.email or False,
            'phone': ledger.phone or ledger.mobile or False,
            'website': ledger.website or False,
            'vat': (ledger.gstin or ledger.vat_number or False) if self.tally_country == 'in' else (
                ledger.vat_number or ledger.gstin or False),
            'customer_rank': 1 if ledger.role == 'receivable' else 0,
            'supplier_rank': 1 if ledger.role == 'payable' else 0,
            'comment': ledger.aliases and env._("Alias in Tally: %s", ledger.aliases) or False,
        }
        Partner = env['res.partner']
        treatment = self.tally_country == 'in' and GST_TREATMENTS.get((ledger.gst_registration_type or '').strip().lower())
        if 'l10n_in_gst_treatment' in Partner._fields and treatment and treatment in dict(
                Partner._fields['l10n_in_gst_treatment'].selection):
            vals['l10n_in_gst_treatment'] = treatment
        if 'l10n_in_pan' in Partner._fields and ledger.pan and self.tally_country == 'in':
            vals['l10n_in_pan'] = ledger.pan
        if ledger.contact:
            vals['child_ids'] = [Command.create({'name': ledger.contact, 'type': 'contact'})]
        return vals

    def _om_tally_create_partner(self, ledger):
        vals = self._om_tally_partner_vals(ledger)
        Partner = self.env['res.partner'].with_company(self.company_id)
        try:
            with self.env.cr.savepoint():
                partner = Partner.create(vals)
        except (ValidationError, UserError) as error:
            self._om_tally_log(self.env._("%(party)s: the tax number %(vat)s was refused (%(error)s), the partner is "
                                          "made without it.", party=ledger.name, vat=vals.get('vat'), error=error),
                               'warning', 'map')
            vals.pop('vat', None)
            vals.pop('l10n_in_pan', None)
            partner = Partner.create(vals)
        return partner

    def action_apply_mapping(self):
        for record in self:
            record._om_tally_apply_masters()
            record.state = 'mapped'
        return True

    def _om_tally_apply_masters(self):
        """ Create the accounts, journals, partners and analytic accounts the mapping asks for; link the others.
        The mapping table keeps what was made, so applying again changes nothing. """
        self.ensure_one()
        env, company = self.env, self.company_id
        Mapping = env['om.tally.mapping']
        Account = env['account.account'].with_company(company)
        self._om_tally_ensure_journals()
        errors = []
        # analytic: made with sudo, the analytic accounting setting may still be off
        Plan, Analytic = env['account.analytic.plan'].sudo(), env['account.analytic.account'].sudo()
        for category in env['om.tally.cost.category'].search([('import_id', '=', self.id)]):
            if not category.analytic_plan_id and category.cost_centre_ids.filtered(
                    lambda c: c.analytic_action == 'create'):
                category.analytic_plan_id = Plan.create({'name': category.name})
        for centre in self.cost_centre_ids:
            if centre.analytic_action == 'create' and not centre.analytic_account_id:
                plan = centre.category_id.analytic_plan_id or Plan.search([], limit=1) or \
                    Plan.create({'name': env._("Cost Centres")})
                centre.analytic_account_id = Analytic.create({
                    'name': centre.name, 'plan_id': plan.id, 'company_id': company.id})
            elif centre.analytic_action == 'link' and not centre.analytic_account_id:
                errors.append(env._("Cost centre %s: choose the analytic account to link.", centre.name))
            if centre.analytic_account_id:
                Mapping._om_tally_set(self, 'cost_centre', centre.guid or centre.name, centre.analytic_account_id,
                                      centre.name, centre.alter_id)
        if self.cost_centre_ids and not env.user.has_group('analytic.group_analytic_accounting'):
            self._om_tally_log(env._("The cost centres became analytic accounts: enable Analytic Accounting in the "
                                     "settings of Accounting to see them."), 'warning', 'map')
        # ledgers of the chart
        for ledger in self.ledger_ids.filtered(lambda l: l.role not in ('receivable', 'payable')):
            if ledger.role in ('bank', 'cash') and ledger.journal_action != 'skip' and ledger.account_action != 'skip':
                journal = ledger.journal_id
                if ledger.journal_action == 'create' and not journal:
                    journal = Mapping._om_tally_find(company, 'journal', ledger.guid, 'account.journal')
                    if not journal:
                        vals = {'name': ledger.name, 'type': ledger.role, 'company_id': company.id,
                                'code': self._om_tally_journal_code(ledger.name)}
                        if ledger.account_action == 'link' and ledger.account_id:
                            vals['default_account_id'] = ledger.account_id.id
                        if ledger.role == 'bank' and ledger.bank_account_number:
                            vals['bank_account_number'] = ledger.bank_account_number
                        journal = env['account.journal'].create(vals)
                elif ledger.journal_action == 'link' and not journal:
                    errors.append(env._("%s: choose the journal to link.", ledger.name))
                    continue
                Mapping._om_tally_set(self, 'journal', ledger.guid or ledger.name, journal, ledger.name,
                                      ledger.alter_id)
                ledger.write({'journal_id': journal.id, 'account_id': journal.default_account_id.id,
                              'account_action': 'link', 'journal_action': 'link'})
            if ledger.account_action == 'link':
                if not ledger.account_id:
                    errors.append(env._("%s: choose the account to link, or create one.", ledger.name))
                    continue
            elif ledger.account_action == 'create':
                account = Mapping._om_tally_find(company, 'ledger', ledger.guid, 'account.account')
                if not account:
                    vals = {
                        'name': ledger.new_account_name or ledger.name,
                        'account_type': ledger.account_type,
                        'company_ids': [Command.link(company.id)],
                        'reconcile': ledger.account_type in ('asset_receivable', 'liability_payable'),
                    }
                    if ledger.new_account_code:
                        vals['code'] = ledger.new_account_code
                    account = Account.create(vals)
                ledger.write({'account_id': account.id, 'account_action': 'link',
                              'match_note': env._("Created")})
            else:
                continue
            Mapping._om_tally_set(self, 'ledger', ledger.guid or ledger.name, ledger.account_id, ledger.name,
                                  ledger.alter_id)
            ledger.is_applied = True
        # parties
        if self.party_ledger_ids.filtered(lambda l: l.partner_action == 'skip') and not self.fallback_partner_id:
            self.fallback_partner_id = env['res.partner'].create({'name': env._("Tally Parties (not imported)"),
                                                                  'is_company': True})
        for ledger in self.party_ledger_ids:
            if ledger.partner_action == 'link' and not ledger.partner_id:
                errors.append(env._("%s: choose the partner to link, or create one.", ledger.name))
                continue
            if ledger.partner_action == 'create' and not ledger.partner_id:
                partner = Mapping._om_tally_find(company, 'party', ledger.guid, 'res.partner') or \
                    self._om_tally_create_partner(ledger)
                ledger.write({'partner_id': partner.id, 'partner_action': 'link',
                              'partner_match_note': env._("Created")})
            if ledger.partner_action == 'link':
                partner = ledger.partner_id.with_company(company)
                field = 'property_account_receivable_id' if ledger.role == 'receivable' else \
                    'property_account_payable_id'
                if ledger.account_id and partner[field] != ledger.account_id:
                    partner[field] = ledger.account_id
                Mapping._om_tally_set(self, 'party', ledger.guid or ledger.name, partner, ledger.name,
                                      ledger.alter_id)
            if not ledger.account_id:
                ledger.account_id = self._om_tally_default_partner_account(ledger.role)
            ledger.is_applied = True
        if errors:
            raise UserError("\n".join(errors[:30]))
        if not self.difference_account_id:
            raise UserError(env._("Choose the account of the opening difference."))
        self._om_tally_log(env._("Accounts, journals, partners and analytic accounts created and linked."), step='map')

    # ------------------------------------------------------------------------------------------------------------
    # balances of Tally

    def _om_tally_in_scope(self, voucher):
        """ The voucher is imported one by one (not inside the opening balances). """
        if not self.cutover_date or voucher.date < self.cutover_date:
            return False
        if self.scope == 'opening':
            return self.sync_enabled
        if self.history_method == 'period':
            return not self.voucher_date_to or voucher.date <= self.voucher_date_to
        return not self.history_date_to or voucher.date <= self.history_date_to

    def _om_tally_balances(self, date_before):
        """ {ledger id: balance} of the ledgers the day before date_before (debit positive). """
        balances = {ledger.id: ledger.opening_balance for ledger in self.ledger_ids}
        if date_before and (not self.books_from or date_before > self.books_from):
            rows = self.env['om.tally.voucher.line']._read_group(
                [('import_id', '=', self.id), ('voucher_id.is_accounting', '=', True), ('date', '<', date_before),
                 ('ledger_id', '!=', False)], ['ledger_id'], ['amount:sum'])
            for ledger, amount in rows:
                balances[ledger.id] = balances.get(ledger.id, 0.0) + amount
        return balances

    def _om_tally_open_bills(self, date_before):
        """ {ledger id: {bill: {amount, date, due}}} of the bills open the day before date_before. """
        bills = defaultdict(dict)
        for bill in self.env['om.tally.ledger.bill'].search([('import_id', '=', self.id)]):
            entry = bills[bill.ledger_id.id].setdefault(bill.name, {'amount': 0.0, 'date': bill.bill_date,
                                                                     'due': bill.due_date})
            entry['amount'] += bill.amount
        if date_before and (not self.books_from or date_before > self.books_from):
            for bill in self.env['om.tally.voucher.bill'].search([
                    ('import_id', '=', self.id), ('voucher_id.is_accounting', '=', True),
                    ('voucher_id.date', '<', date_before), ('bill_type', '!=', 'on_account'), ('name', '!=', False)]):
                entry = bills[bill.line_id.ledger_id.id].setdefault(bill.name, {
                    'amount': 0.0, 'date': bill.voucher_id.date, 'due': bill.due_date})
                entry['amount'] += bill.amount
        return bills

    def _om_tally_target(self, ledger):
        """ (account, partner) a ledger posts to; no account for a skipped ledger. """
        if ledger.role in ('receivable', 'payable'):
            partner = self.fallback_partner_id if ledger.partner_action == 'skip' else ledger.partner_id
            return ledger.account_id or self._om_tally_default_partner_account(ledger.role), partner
        if ledger.account_action == 'skip':
            return self.env['account.account'], self.env['res.partner']
        return ledger.account_id, self.env['res.partner']

    def _om_tally_opening_lines(self):
        """ The lines of the opening entry: dicts with ledger, account, partner, amount, name, due date, bill. """
        self.ensure_one()
        currency = self.currency_id
        balances = self._om_tally_balances(self.cutover_date)
        bills = self._om_tally_open_bills(self.cutover_date)
        lines, skipped, excluded = [], [], []
        for ledger in self.ledger_ids.sorted(lambda l: (l.role or '', l.name)):
            balance = currency.round(balances.get(ledger.id, 0.0))
            if currency.is_zero(balance):
                continue
            if ledger.role == 'stock' and self.exclude_stock_in_hand:
                excluded.append((ledger, balance))
                continue
            account, partner = self._om_tally_target(ledger)
            if not account:
                skipped.append((ledger, balance))
                if self.accept_difference and self.suspense_account_id:
                    lines.append({'ledger': ledger, 'account': self.suspense_account_id, 'partner': partner,
                                  'amount': balance, 'name': self.env._("%s (skipped)", ledger.name)})
                continue
            if ledger.role in ('receivable', 'payable') and bills.get(ledger.id):
                rest = balance
                for bill_name, bill in sorted(bills[ledger.id].items(), key=lambda item: (item[1]['date'] or
                                                                                         self.cutover_date, item[0])):
                    amount = currency.round(bill['amount'])
                    if currency.is_zero(amount):
                        continue
                    rest -= amount
                    lines.append({'ledger': ledger, 'account': account, 'partner': partner, 'amount': amount,
                                  'name': bill_name, 'date_maturity': bill['due'] or bill['date'],
                                  'bill': ('new', bill_name)})
                if not currency.is_zero(rest):
                    lines.append({'ledger': ledger, 'account': account, 'partner': partner,
                                  'amount': currency.round(rest), 'name': self.env._("Opening balance")})
            else:
                lines.append({'ledger': ledger, 'account': account, 'partner': partner, 'amount': balance,
                              'name': ledger.name})
        total = sum(line['amount'] for line in lines)
        if not (self.accept_difference and self.suspense_account_id):
            # skipped ledgers stay out: the entry is posted only once they are accepted (suspense)
            total += sum(amount for _ledger, amount in skipped)
        total = currency.round(total)
        if not currency.is_zero(total):
            lines.append({'ledger': False, 'account': self.difference_account_id, 'partner': self.env['res.partner'],
                          'amount': -total, 'name': self.env._("Difference in opening balances")})
        return lines, skipped, excluded

    # ------------------------------------------------------------------------------------------------------------
    # the check

    def action_compute_check(self):
        for record in self:
            if record.state not in ('mapped', 'checked', 'done'):
                raise UserError(self.env._("Create and link the accounts first."))
            record._om_tally_compute_check()
            if record.state == 'mapped':
                record.state = 'checked'
        return True

    def _om_tally_ensure_suspense(self):
        if self.accept_difference and not self.suspense_account_id:
            vals = {'name': self.env._("Tally Suspense"), 'account_type': 'liability_current',
                    'company_ids': [Command.link(self.company_id.id)]}
            code = self._om_tally_new_code('liability_current', self._om_tally_accounts(), set())
            if code:
                vals['code'] = code
            self.suspense_account_id = self.env['account.account'].create(vals)

    def _om_tally_compute_check(self, verify=False):
        """ Trial balance per Odoo account: Tally's balance, what the import posts (or posted, to verify), and
        what Odoo already holds. """
        self.ensure_one()
        env, currency = self.env, self.currency_id
        if not self.cutover_date:
            raise UserError(env._("Enter the cut-over date."))
        self._om_tally_ensure_suspense()
        if self.scope == 'opening':
            end = self.cutover_date
        elif self.history_method == 'period' and self.voucher_date_to:
            end = self.voucher_date_to + timedelta(days=1)
        elif self.history_date_to:
            end = self.history_date_to + timedelta(days=1)
        else:
            end = max(self.voucher_ids.mapped('date') or [self.cutover_date]) + timedelta(days=1)
        tally_balances = self._om_tally_balances(end)
        rows = {}

        def row(key, account=None, label=None):
            if key not in rows:
                rows[key] = {'account_id': account.id if account else False, 'label': label or (
                    account.display_name if account else ''), 'tally_balance': 0.0, 'posted_balance': 0.0,
                    'note': False, 'is_explained': False, 'ledgers': set()}
            return rows[key]

        excluded_total = 0.0
        for ledger in self.ledger_ids:
            balance = currency.round(tally_balances.get(ledger.id, 0.0))
            if currency.is_zero(balance):
                continue
            if ledger.role == 'stock' and self.exclude_stock_in_hand:
                target = row(('stock', ledger.id), label=env._("%s (left out)", ledger.name))
                target.update(note=env._("Left out: in the opening difference account"), is_explained=True)
                excluded_total += currency.round(self._om_tally_balances(self.cutover_date).get(ledger.id, 0.0))
            else:
                account, _partner = self._om_tally_target(ledger)
                target = row(account.id, account) if account else row(('skip', ledger.id), label=env._(
                    "%s (skipped)", ledger.name))
                if not account:
                    accepted = self.accept_difference and self.suspense_account_id
                    target['note'] = env._("Skipped: to the suspense account") if accepted else env._("Skipped ledger")
                    target['is_explained'] = bool(accepted)
            target['tally_balance'] += balance
            target['ledgers'].add(ledger.name)
        if not currency.is_zero(self.opening_difference):
            target = row(self.difference_account_id.id, self.difference_account_id)
            target['tally_balance'] -= self.opening_difference
            target['ledgers'].add(env._("Difference in opening balances"))
        if verify:
            moves = self.opening_move_id | self.voucher_ids.move_id
            for account, balance in env['account.move.line']._read_group(
                    [('move_id', 'in', moves.ids), ('parent_state', '=', 'posted')], ['account_id'], ['balance:sum']):
                row(account.id, account)['posted_balance'] += balance
        else:
            lines, _skipped, _excluded = self._om_tally_opening_lines()
            for line in lines:
                target = row(line['account'].id, line['account'])
                target['posted_balance'] += line['amount']
                if line['account'] == self.suspense_account_id and self.accept_difference:
                    target.update(is_explained=True, note=env._("Accepted differences"))
            unbalanced = 0.0
            vouchers = self.voucher_ids.filtered(lambda v: v.is_accounting and self._om_tally_in_scope(v)
                                                 and v.state != 'skipped')
            for voucher in vouchers:
                for line in voucher.line_ids:
                    account, _partner = self._om_tally_target(line.ledger_id) if line.ledger_id else (
                        env['account.account'], False)
                    if account:
                        row(account.id, account)['posted_balance'] += line.amount
                    elif self.accept_difference and self.suspense_account_id:
                        target = row(self.suspense_account_id.id, self.suspense_account_id)
                        target['posted_balance'] += line.amount
                        target.update(is_explained=True, note=env._("Accepted differences"))
                    else:
                        unbalanced += line.amount
            if not currency.is_zero(unbalanced):
                target = row('unbalanced', label=env._("Not posted: lines of skipped or unknown ledgers"))
                target['posted_balance'] += unbalanced
        if excluded_total and self.difference_account_id.id in rows:
            rows[self.difference_account_id.id]['note'] = env._("Includes the Stock-in-Hand left out")
        # what Odoo holds already on these accounts, outside this import
        account_ids = [values['account_id'] for values in rows.values() if values['account_id']]
        own_moves = (self.opening_move_id | self.voucher_ids.move_id).ids
        existing = dict(env['account.move.line']._read_group(
            [('account_id', 'in', account_ids), ('parent_state', '=', 'posted'), ('company_id', '=', self.company_id.id),
             ('date', '<', self.cutover_date), ('move_id', 'not in', own_moves)],
            ['account_id'], ['balance:sum'])) if account_ids else {}
        self.check_line_ids.unlink()
        vals_list = []
        for values in rows.values():
            account = env['account.account'].browse(values['account_id'])
            difference = currency.round(values['tally_balance'] - values['posted_balance'])
            explained = values['is_explained']
            if account == self.difference_account_id and excluded_total:
                explained = currency.is_zero(difference + excluded_total)
            if currency.is_zero(values['tally_balance']) and currency.is_zero(values['posted_balance']):
                continue
            vals_list.append({
                'import_id': self.id, 'account_id': account.id, 'label': values['label'],
                'ledger_names': ", ".join(sorted(values['ledgers']))[:500],
                'tally_balance': currency.round(values['tally_balance']),
                'posted_balance': currency.round(values['posted_balance']),
                'existing_balance': currency.round(existing.get(account, 0.0)) if account else 0.0,
                'note': values['note'], 'is_explained': explained,
            })
        env['om.tally.check.line'].create(vals_list)
        self.check_date = fields.Datetime.now()
        self._om_tally_log(env._("Trial balance %(what)s: %(rows)s accounts, difference to explain %(diff)s.",
                                 what=env._("verified") if verify else env._("checked"), rows=len(vals_list),
                                 diff=f"{self.check_difference:,.2f}"), step='check')

    # ------------------------------------------------------------------------------------------------------------
    # posting

    def action_post(self):
        for record in self:
            if record.state != 'checked':
                raise UserError(self.env._("Run the check first."))
            record._om_tally_compute_check()
            if not record.currency_id.is_zero(record.check_difference) and not record.accept_difference:
                raise UserError(self.env._(
                    "Tally and Odoo differ by %s: fix the mapping, or accept the differences (they go to the "
                    "suspense account).", f"{record.check_difference:,.2f}"))
            record._om_tally_ensure_suspense()
            record._om_tally_post_opening()
            # vouchers of later periods stay to import
            to_skip = record.voucher_ids.filtered(lambda v: v.state == 'staged' and (
                not v.is_accounting or v.date < record.cutover_date
                or (record.scope == 'opening' and not record.sync_enabled)))
            to_skip.write({'state': 'skipped'})
            record.state = 'posting'
            record._om_tally_log(self.env._("Posting started: %s vouchers to import.", record.post_total), step='post')
            record._om_tally_trigger_posting()
        return True

    def _om_tally_trigger_posting(self):
        self.env.ref('om_tally_account.ir_cron_om_tally_post')._trigger()

    def _om_tally_move_line_vals(self, line):
        amount = line['amount']
        vals = {
            'account_id': line['account'].id,
            'partner_id': line['partner'].id if line.get('partner') else False,
            'name': line.get('name') or '/',
            'debit': amount if amount > 0 else 0.0,
            'credit': -amount if amount < 0 else 0.0,
        }
        if line.get('date_maturity'):
            vals['date_maturity'] = line['date_maturity']
        if line.get('analytic'):
            vals['analytic_distribution'] = line['analytic']
        return vals

    def _om_tally_post_opening(self):
        self.ensure_one()
        Mapping = self.env['om.tally.mapping']
        key = f'opening|{self.tally_company_guid or self.tally_company_name}|{self.cutover_date}'
        move = self.opening_move_id or Mapping._om_tally_find(self.company_id, 'opening', key, 'account.move')
        if move:
            self.opening_move_id = move
            return move
        lines, _skipped, _excluded = self._om_tally_opening_lines()
        lines = [line for line in lines if not self.currency_id.is_zero(line['amount'])]
        if not lines:
            return self.env['account.move']
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.opening_journal_id.id,
            'date': self.cutover_date - timedelta(days=1),
            'ref': self.env._("Opening balances from Tally: %s", self.tally_company_name or self.name),
            'company_id': self.company_id.id,
            'line_ids': [Command.create(self._om_tally_move_line_vals(line)) for line in lines],
        })
        move.action_post()
        self._om_tally_register_bills(move.line_ids.sorted('id'), lines)
        Mapping._om_tally_set(self, 'opening', key, move, move.ref)
        self.opening_move_id = move
        self._om_tally_log(self.env._("Opening entry %(move)s posted with %(lines)s lines.", move=move.name,
                                      lines=len(lines)), step='post')
        return move

    def _om_tally_bill_key(self, ledger, bill_name):
        return f"{ledger.guid or ledger.name}|{bill_name}"

    def _om_tally_register_bills(self, move_lines, lines):
        """ New Ref: remember the move line of the bill. Agst Ref: reconcile with it. """
        Mapping = self.env['om.tally.mapping']
        for move_line, line in zip(move_lines, lines):
            for bill_type, bill_name in line.get('bills') or ([line['bill']] if line.get('bill') else []):
                if not bill_name:
                    continue
                key = self._om_tally_bill_key(line['ledger'], bill_name)
                known = Mapping._om_tally_find(self.company_id, 'bill', key, 'account.move.line')
                if not known and bill_type in ('new', 'advance'):
                    Mapping._om_tally_set(self, 'bill', key, move_line, f"{line['ledger'].name}: {bill_name}")
                elif known and known != move_line:
                    self._om_tally_reconcile(known, move_line, bill_name)
                elif not known:
                    self._om_tally_log(self.env._("%(party)s: bill %(bill)s was not found to reconcile.",
                                                  party=line['ledger'].name, bill=bill_name), 'warning', 'post')

    def _om_tally_reconcile(self, bill_line, move_line, bill_name):
        if bill_line.account_id != move_line.account_id or not bill_line.account_id.reconcile:
            return False
        if bill_line.reconciled or move_line.reconciled or \
                (bill_line.amount_residual > 0) == (move_line.amount_residual > 0):
            return False
        try:
            with self.env.cr.savepoint():
                (bill_line | move_line).reconcile()
        except (UserError, ValidationError) as error:
            self._om_tally_log(self.env._("Bill %(bill)s not reconciled: %(error)s", bill=bill_name, error=error),
                               'warning', 'post')
            return False
        return True

    def _om_tally_analytic(self, line):
        """ The analytic distribution of a ledger entry, from its cost centre allocations. """
        if not line.cost_ids or not line.amount:
            return False
        distribution = defaultdict(float)
        for cost in line.cost_ids:
            account = cost.cost_centre_id.analytic_account_id
            if account:
                distribution[str(account.id)] += round(100.0 * cost.amount / line.amount, 4)
        return dict(distribution) or False

    def _om_tally_exact_lines(self, voucher):
        lines = []
        currency = self.currency_id
        for line in voucher.line_ids:
            ledger = line.ledger_id
            if not ledger:
                raise UserError(self.env._("Ledger %s was not read from Tally.", line.ledger_name))
            account, partner = self._om_tally_target(ledger)
            if not account:
                if self.accept_difference and self.suspense_account_id:
                    account = self.suspense_account_id
                else:
                    raise UserError(self.env._("Ledger %s is skipped.", ledger.name))
            name = ledger.name if not voucher.narration else f"{ledger.name}: {voucher.narration}"[:250]
            base = {'ledger': ledger, 'account': account, 'partner': partner, 'name': name,
                    'analytic': self._om_tally_analytic(line)}
            bills = line.bill_ids.filtered(lambda b: b.name and b.bill_type != 'on_account')
            if ledger.role in ('receivable', 'payable') and bills:
                rest = line.amount
                for bill in bills:
                    rest -= bill.amount
                    lines.append(dict(base, amount=bill.amount, name=f"{ledger.name}: {bill.name}",
                                      date_maturity=bill.due_date, bill=(bill.bill_type, bill.name)))
                if not currency.is_zero(rest):
                    lines.append(dict(base, amount=currency.round(rest)))
            else:
                lines.append(dict(base, amount=line.amount))
        total = currency.round(sum(line['amount'] for line in lines))
        if not currency.is_zero(total):
            if not (self.accept_difference and self.suspense_account_id):
                raise UserError(self.env._("The voucher is off by %s.", total))
            lines.append({'ledger': False, 'account': self.suspense_account_id, 'partner': False, 'amount': -total,
                          'name': self.env._("Unbalanced in Tally")})
        return lines

    def _om_tally_voucher_ref(self, voucher):
        ref = voucher.display_number
        if voucher.reference:
            ref = f"{ref} ({voucher.reference})"
        return ref

    def _om_tally_post_exact(self, voucher, journal=None):
        lines = self._om_tally_exact_lines(voucher)
        journal = journal or voucher.voucher_type_id.journal_id or self.import_journal_id
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': voucher.date,
            'ref': self._om_tally_voucher_ref(voucher),
            'narration': voucher.narration or False,
            'company_id': self.company_id.id,
            'line_ids': [Command.create(self._om_tally_move_line_vals(line)) for line in lines],
        })
        move.action_post()
        self._om_tally_register_bills(move.line_ids.sorted('id'), lines)
        return move

    def _om_tally_inventory_line_vals(self, inventory_line):
        """ Hook: the product of an inventory line (om_tally_stock). """
        return {}

    def _om_tally_voucher_taxes(self, voucher, tax_lines, direction, base_amount):
        """ The taxes of Odoo for the tax ledgers of a voucher, or None when they cannot all be found. """
        taxes = self.env['account.tax']
        for line in tax_lines:
            ledger = line.ledger_id
            rate = round(100.0 * abs(line.amount) / base_amount, 2) if base_amount else 0.0
            tax = ledger.tax_id if ledger.tax_id and (not ledger.tax_id.amount or
                                                      abs(ledger.tax_id.amount - rate) < 0.05) else \
                self._om_tally_find_tax(ledger, direction, rate)
            if not tax:
                return None
            taxes |= tax
        if taxes and all(tax.type_tax_use == 'none' for tax in taxes):
            group = self.env['account.tax'].search([
                ('company_id', '=', self.company_id.id), ('amount_type', '=', 'group'),
                ('type_tax_use', '=', direction)]).filtered(lambda g: g.children_tax_ids == taxes)[:1]
            taxes = group or None
        if taxes and any(tax.type_tax_use != direction for tax in taxes):
            return None
        if taxes and not all(taxes.mapped('active')):
            return None
        return taxes

    def _om_tally_post_document(self, voucher):
        """ The voucher as an invoice, bill or refund, or posted in its bank journal; None: exact entry. """
        base = voucher.base_type
        party_lines = voucher.line_ids.filtered(lambda l: l.ledger_id.role in ('receivable', 'payable'))
        if base in ('Sales', 'Credit Note', 'Purchase', 'Debit Note') and len(party_lines.ledger_id) == 1:
            return self._om_tally_post_invoice(voucher, party_lines)
        if base in ('Receipt', 'Payment', 'Contra'):
            bank = voucher.line_ids.ledger_id.filtered(lambda l: l.role in ('bank', 'cash') and l.journal_id)[:1]
            if bank:
                return self._om_tally_post_exact(voucher, journal=voucher.voucher_type_id.journal_id or bank.journal_id)
        return None

    def _om_tally_post_invoice(self, voucher, party_lines):
        env, currency = self.env, self.currency_id
        ledger = party_lines.ledger_id
        move_type = INVOICE_TYPES.get((voucher.base_type, ledger.role))
        party_amount = currency.round(sum(party_lines.mapped('amount')))
        if not move_type or currency.is_zero(party_amount) or \
                (party_amount > 0) != (move_type in ('out_invoice', 'in_refund')):
            return None
        sign = -1 if move_type in ('out_invoice', 'in_refund') else 1
        direction = 'sale' if move_type.startswith('out') else 'purchase'
        account_party, partner = self._om_tally_target(ledger)
        others = voucher.line_ids - party_lines
        tax_lines = others.filtered(lambda l: l.ledger_id.role == 'tax' and l.ledger_id.tax_type not in ('TDS', 'TCS'))
        ledgers = {line.ledger_name: line.ledger_id for line in voucher.line_ids}
        product_lines, extra_lines = [], []
        taxable_base = 0.0
        if voucher.inventory_ids:
            inward_expected = move_type in ('out_refund', 'in_invoice')
            item_ledger_lines = others.filtered('from_inventory')
            for inventory in voucher.inventory_ids:
                item_ledger = ledgers.get(inventory.ledger_name) or item_ledger_lines.ledger_id[:1]
                account, _partner = self._om_tally_target(item_ledger) if item_ledger else (False, False)
                if not account or not inventory.amount:
                    return None
                quantity = inventory.quantity or 1.0
                amount = inventory.amount if inventory.is_inward == inward_expected else -inventory.amount
                cost_lines = item_ledger_lines.filtered(lambda l: l.ledger_id == item_ledger)
                vals = {
                    'name': inventory.item_name + (f" ({inventory.batch_name})" if inventory.batch_name
                                                   and inventory.batch_name != 'Primary Batch' else ''),
                    'quantity': quantity,
                    'price_unit': amount / quantity,
                    'account_id': account.id,
                    'analytic_distribution': self._om_tally_analytic(cost_lines[:1]) if cost_lines else False,
                }
                vals.update(self._om_tally_inventory_line_vals(inventory))
                product_lines.append(vals)
                taxable_base += abs(amount)
            rest = others - tax_lines - item_ledger_lines
        else:
            rest = others - tax_lines
        for line in rest:
            account, _partner = self._om_tally_target(line.ledger_id)
            if not account:
                return None
            vals = {'name': line.ledger_id.name, 'quantity': 1.0, 'price_unit': sign * line.amount,
                    'account_id': account.id, 'analytic_distribution': self._om_tally_analytic(line)}
            if line.ledger_id.primary_group in ('Sales Accounts', 'Purchase Accounts'):
                product_lines.append(vals)
                taxable_base += abs(line.amount)
            else:
                extra_lines.append(vals)
        if not product_lines:
            # an invoice of services in accounting mode: the income or expense ledgers carry the tax
            for line, vals in zip(rest, list(extra_lines)):
                if line.ledger_id.nature in ('income', 'expense'):
                    extra_lines.remove(vals)
                    product_lines.append(vals)
                    taxable_base += abs(line.amount)
        taxes = self._om_tally_voucher_taxes(voucher, tax_lines, direction, taxable_base) if tax_lines else None
        due_dates = [bill.due_date for bill in party_lines.bill_ids if bill.bill_type == 'new' and bill.due_date]
        header = {
            'move_type': move_type,
            'partner_id': partner.id,
            'journal_id': voucher.voucher_type_id.journal_id.id if voucher.voucher_type_id.journal_id.type in (
                'sale', 'purchase') else False,
            'invoice_date': voucher.date,
            'date': voucher.date,
            'ref': (voucher.reference or voucher.number) if direction == 'purchase' else voucher.display_number,
            'payment_reference': voucher.number,
            'narration': voucher.narration or False,
            'fiscal_position_id': False,
            'invoice_payment_term_id': False,
            'invoice_date_due': max(due_dates) if due_dates else voucher.date,
            'company_id': self.company_id.id,
        }
        if not header['journal_id']:
            header.pop('journal_id')

        def build(with_taxes):
            lines = []
            for vals in product_lines:
                lines.append(dict(vals, tax_ids=[Command.set(taxes.ids)] if with_taxes else [Command.clear()]))
            for vals in extra_lines:
                lines.append(dict(vals, tax_ids=[Command.clear()]))
            if not with_taxes:
                for line in tax_lines:
                    account, _partner = self._om_tally_target(line.ledger_id)
                    if not account:
                        return None
                    lines.append({'name': line.ledger_id.name, 'quantity': 1.0, 'price_unit': sign * line.amount,
                                  'account_id': account.id, 'tax_ids': [Command.clear()]})
            move = env['account.move'].with_company(self.company_id).create(
                dict(header, invoice_line_ids=[Command.create(vals) for vals in lines]))
            if move.partner_id and ledger.account_id:
                term_lines = move.line_ids.filtered(lambda l: l.display_type == 'payment_term')
                if term_lines.account_id != ledger.account_id:
                    term_lines.account_id = ledger.account_id
            if not currency.is_zero(move.amount_total - abs(party_amount)):
                move.unlink()
                return None
            return move

        move = build(True) if taxes else None
        if not move:
            move = build(False)
        if not move:
            return None
        move.action_post()
        term_line = move.line_ids.filtered(lambda l: l.display_type == 'payment_term')[:1]
        bills = [(bill.bill_type, bill.name) for bill in party_lines.bill_ids
                 if bill.name and bill.bill_type != 'on_account']
        self._om_tally_register_bills(term_line, [{'ledger': ledger, 'bills': bills}])
        return move

    def _om_tally_post_voucher(self, voucher):
        Mapping = self.env['om.tally.mapping']
        move = Mapping._om_tally_find(self.company_id, 'voucher', voucher.guid, 'account.move')
        if not move:
            if self.history_mode == 'documents':
                move = self._om_tally_post_document(voucher)
            if not move:
                move = self._om_tally_post_exact(voucher)
            Mapping._om_tally_set(self, 'voucher', voucher.guid, move, voucher.display_number, voucher.alter_id)
        voucher.write({'state': 'posted', 'move_id': move.id, 'error_message': False})
        return move

    def _om_tally_vouchers_to_post(self, limit=None):
        vouchers = self.env['om.tally.voucher'].search([
            ('import_id', '=', self.id), ('state', '=', 'staged'), ('is_accounting', '=', True),
            ('date', '>=', self.cutover_date)], order='date, id')
        vouchers = vouchers.filtered(self._om_tally_in_scope)
        return vouchers[:limit] if limit else vouchers

    def _om_tally_post_batch(self, limit=None):
        """ Post up to limit vouchers; each in its own savepoint, an error marks the voucher only. """
        self.ensure_one()
        vouchers = self._om_tally_vouchers_to_post(limit or self.post_batch_size or 200)
        for voucher in vouchers:
            try:
                with self.env.cr.savepoint():
                    self._om_tally_post_voucher(voucher)
            except Exception as error:  # pylint: disable=broad-except
                _logger.info("Tally voucher %s not imported: %s", voucher.id, error)
                voucher.write({'state': 'error', 'error_message': str(error)})
        if not self._om_tally_vouchers_to_post(1):
            self.state = 'done'
            self._om_tally_period_imported()
            self._om_tally_log(self.env._("Posting finished: %(done)s vouchers imported, %(errors)s in error. Set the "
                                          "lock date to %(date)s in the accounting settings once checked.",
                                          done=self.post_done, errors=self.post_error,
                                          date=self.cutover_date - timedelta(days=1)), step='post')
        return len(vouchers)

    @api.model
    def _cron_om_tally_post(self):
        Cron = self.env['ir.cron']
        for record in self.search([('state', '=', 'posting')]):
            while record.state == 'posting':
                processed = record.with_company(record.company_id)._om_tally_post_batch()
                remaining = len(record._om_tally_vouchers_to_post())
                if Cron._commit_progress(processed, remaining=remaining) <= 0:
                    return

    def action_post_now(self):
        """ Post the next batch at once, without waiting for the scheduled job. """
        for record in self.filtered(lambda r: r.state == 'posting'):
            record._om_tally_post_batch()
        return True

    def action_verify(self):
        for record in self:
            record._om_tally_compute_check(verify=True)
        return True

    def action_open_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.env._("Entries from Tally"), 'res_model': 'account.move',
            'view_mode': 'list,form', 'domain': [('id', 'in', (self.opening_move_id | self.voucher_ids.move_id).ids)],
        }

    def action_open_errors(self):
        action = self.action_open_vouchers()
        action['domain'] = action['domain'] + [('state', '=', 'error')]
        return action

    # periods

    def _om_tally_current_period(self):
        """ (first day, last day) of the period being read and imported. """
        dates = self.voucher_ids.mapped('date')
        date_to = self.voucher_date_to or (max(dates) if dates else self.cutover_date)
        return max(self.voucher_date_from or self.cutover_date, self.cutover_date), date_to

    def _om_tally_after_read(self):
        res = super()._om_tally_after_read()
        for record in self.filtered(lambda r: r.scope == 'history' and r.history_method == 'period'
                                    and r.cutover_date):
            date_from, date_to = record._om_tally_current_period()
            period = record.period_ids.filtered(lambda p: p.date_to == date_to)
            if period:
                period.date_from = date_from
            else:
                self.env['om.tally.period'].create({'import_id': record.id, 'date_from': date_from,
                                                    'date_to': date_to})
        return res

    def _om_tally_period_imported(self):
        if self.scope == 'history' and self.history_method == 'period':
            self.period_ids.filtered(lambda p: p.state == 'read').write({'state': 'imported'})

    def action_next_period(self):
        """ Prepare the next period: read its vouchers (or its file), check and import them. """
        for record in self:
            last = max(record.period_ids.mapped('date_to') or [record.voucher_date_to or record.cutover_date])
            date_from = last + timedelta(days=1)
            record.write({
                'voucher_date_from': date_from,
                'voucher_date_to': date_from + relativedelta(years=1, days=-1),
                'state': 'analyzed',
            })
            record.check_line_ids.unlink()
            record._om_tally_log(self.env._("Next period: %(start)s to %(end)s.", start=date_from,
                                            end=record.voucher_date_to), step='read')
        return True

    # a new company of Odoo from the details of Tally

    def action_create_company(self):
        """ Make an Odoo company from the Tally company: name, country, currency, tax number, address and fiscal
        year (April to March in India, January to December in the Gulf). """
        self.ensure_one()
        env = self.env
        codes = {'in': ('IN', 'INR', '3'), 'ae': ('AE', 'AED', '12'), 'sa': ('SA', 'SAR', '12'),
                 'bh': ('BH', 'BHD', '12')}
        country_code, currency_code, last_month = codes.get(self.tally_country, (False, False, '12'))
        country = env['res.country'].search([('code', '=', country_code)], limit=1) if country_code else \
            env['res.country'].search([('name', '=ilike', self.tally_country_name)], limit=1)
        currency = env['res.currency'].with_context(active_test=False).search(
            [('name', '=', currency_code)], limit=1) if currency_code else country.currency_id
        if currency and not currency.active:
            currency.active = True
        state = env['res.country.state'].search([('name', '=ilike', self.tally_state_name),
                                                 ('country_id', '=', country.id)], limit=1) \
            if self.tally_state_name and country else env['res.country.state']
        lines = [line.strip() for line in (self.tally_address or '').splitlines() if line.strip()]
        vals = {
            'name': self.tally_mailing_name or self.tally_company_name or self.name,
            'country_id': country.id,
            'state_id': state.id,
            'currency_id': currency.id or self.company_id.currency_id.id,
            'street': lines[0] if lines else False,
            'city': lines[-1] if len(lines) > 1 else False,
            'zip': self.tally_pincode or False,
            'email': self.tally_email or False,
            'phone': self.tally_phone or False,
            'fiscalyear_last_month': last_month,
            'fiscalyear_last_day': 31,
        }
        name, number = vals['name'], 1
        while env['res.company'].sudo().search_count([('name', '=', vals['name'])]):
            number += 1
            vals['name'] = f"{name} ({number})"
        company = env['res.company'].create({key: value for key, value in vals.items() if value is not False})
        if self.tally_gstin:
            try:
                with env.cr.savepoint():
                    company.vat = self.tally_gstin
            except (ValidationError, UserError):
                self._om_tally_log(env._("The tax number %s of the company was refused: enter it by hand.",
                                         self.tally_gstin), 'warning', 'connect')
        env.user.company_ids = [Command.link(company.id)]
        ChartTemplate = env['account.chart.template']
        template = ChartTemplate._guess_chart_template(country) if country else 'generic_coa'
        if template not in ChartTemplate._get_chart_template_mapping():
            self._om_tally_log(env._("Install the accounting localization of %s for its chart of accounts and "
                                     "taxes: the generic chart was loaded.", country.name or '-'), 'warning', 'connect')
            template = 'generic_coa'
        ChartTemplate.try_loading(template, company, install_demo=False)
        self.company_id = company
        self._om_tally_log(env._("Odoo company %s made from the Tally company.", company.name), step='connect')
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_back_to_mapping(self):
        self.filtered(lambda r: r.state in ('mapped', 'checked')).write({'state': 'analyzed'})
        return True

    def _om_tally_after_sync(self, vouchers):
        res = super()._om_tally_after_sync(vouchers)
        if self.sync_enabled and self.state in ('done', 'posting'):
            changed = vouchers.filtered('is_changed')
            if changed:
                self._om_tally_log(self.env._("%s imported vouchers were changed in Tally: check them.", len(changed)),
                                   'warning', 'sync')
            if self._om_tally_vouchers_to_post(1):
                self.state = 'posting'
                self._om_tally_trigger_posting()
        return res
