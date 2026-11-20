from odoo import api, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

ACCOUNT_TYPES = {
    'customer': ('asset_receivable',),
    'supplier': ('liability_payable',),
    'customer_supplier': ('asset_receivable', 'liability_payable'),
}


class OmDynamicReportPartnerLedger(models.AbstractModel):
    """Partner Ledger: every partner with its debit, credit and balance on the
    receivable and payable accounts; a partner unfolds into its initial
    balance and its journal items, with due dates and matching numbers."""
    _name = 'om.dynamic.report.partner.ledger'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Partner Ledger'

    _report_name = 'Partner Ledger'
    _report_description = _lt("What each customer and vendor owes or is owed, entry by entry.")
    _report_section = 'partners'
    _report_sequence = 30
    _report_icon = 'person'
    _report_group = 'account.group_account_invoice,account.group_account_readonly'

    @api.model
    def _om_report_title(self):
        return self.env._("Partner Ledger")

    @api.model
    def _om_name_label(self, options):
        return self.env._("Partner")

    @api.model
    def _om_filters(self):
        filters = self._odr_filters('partner_ids', 'partner_category_ids', 'journal_ids', 'account_ids', 'aml_filter_ids')
        for spec in filters:
            if spec['key'] == 'account_ids':
                spec['domain'] = spec['domain'] + [
                    ('account_type', 'in', ('asset_receivable', 'liability_payable'))]
        return filters

    @api.model
    def _om_toggles(self):
        return [
            {'key': 'initial_balance', 'label': self.env._("Initial balance"), 'default': True,
             'help': self.env._("Start each partner with its balance before the period.")},
            {'key': 'reconciled', 'label': self.env._("Include reconciled entries"), 'default': True,
             'help': self.env._("Without it, only the entries still open are shown.")},
        ]

    @api.model
    def _om_choices(self):
        return [
            self._odr_target_move_choice(),
            {'key': 'result_selection', 'label': self.env._("Accounts"), 'icon': 'account_balance_wallet',
             'menu': 'bar', 'default': 'customer_supplier', 'choices': [
                 ['customer_supplier', self.env._("Receivable and Payable")],
                 ['customer', self.env._("Receivable")],
                 ['supplier', self.env._("Payable")],
             ]},
            {'key': 'balance_filter', 'label': self.env._("Partners"), 'default': 'all', 'choices': [
                ['all', self.env._("All partners with entries")],
                ['not_zero', self.env._("With balance not zero")],
                ['debit', self.env._("With a debit balance")],
                ['credit', self.env._("With a credit balance")],
            ]},
        ]

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'date', 'label': self.env._("Date"), 'type': 'date', 'detail_only': True},
            {'key': 'journal', 'label': self.env._("Journal"), 'type': 'char', 'detail_only': True},
            {'key': 'account', 'label': self.env._("Account"), 'type': 'char', 'detail_only': True},
            {'key': 'label', 'label': self.env._("Label"), 'type': 'char', 'detail_only': True},
            {'key': 'date_maturity', 'label': self.env._("Due Date"), 'type': 'date', 'detail_only': True},
            {'key': 'matching', 'label': self.env._("Matching"), 'type': 'char', 'detail_only': True},
            {'key': 'amount_currency', 'label': self.env._("Amount in Currency"), 'type': 'float',
             'detail_only': True, 'visible': False},
            {'key': 'currency', 'label': self.env._("Currency"), 'type': 'char', 'detail_only': True,
             'visible': False},
            {'key': 'debit', 'label': self.env._("Debit"), 'type': 'monetary', 'blank_zero': True},
            {'key': 'credit', 'label': self.env._("Credit"), 'type': 'monetary', 'blank_zero': True},
            {'key': 'balance', 'label': self.env._("Balance"), 'type': 'monetary'},
        ]

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    @api.model
    def _odr_partner_domain(self, options):
        domain = self._odr_domain(options) + [
            ('partner_id', '!=', False),
            ('account_id.account_type', 'in', ACCOUNT_TYPES[options['result_selection']]),
        ]
        if not options['reconciled']:
            domain.append(('full_reconcile_id', '=', False))
        return domain

    @api.model
    def _odr_tree(self, options):
        empty = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}
        domain = self._odr_partner_domain(options)
        period = self._odr_sums(domain + self._odr_period_domain(options), 'partner_id')
        initial = {}
        if options['initial_balance'] and options.get('date_from'):
            # receivable and payable accounts carry their whole history
            initial = self._odr_sums(domain + [('date', '<', options['date_from'])], 'partner_id')
        currency = self._om_currency()
        partners = self.env['res.partner'].with_context(active_test=False).browse(set(period) | set(initial))
        nodes = []
        total = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}
        for partner in partners.sorted(lambda p: (p.display_name or '').casefold()):
            opening = initial.get(partner.id, empty)
            values = {key: opening[key] + period.get(partner.id, empty)[key] for key in ('debit', 'credit', 'balance')}
            balance = values['balance']
            if options['balance_filter'] == 'not_zero' and currency.is_zero(balance):
                continue
            if options['balance_filter'] == 'debit' and (currency.is_zero(balance) or balance < 0):
                continue
            if options['balance_filter'] == 'credit' and (currency.is_zero(balance) or balance > 0):
                continue
            if partner.id not in period and currency.is_zero(opening['balance']):
                continue
            line_id = 'partner-%s' % partner.id
            line = self._om_line(line_id, partner.display_name, values, kind='leaf', has_children=True,
                                 open_record=('res.partner', partner.id), drill=True,
                                 drill_label=self.env._("Journal items of the period"),
                                 opening=opening if partner.id in initial else False)
            nodes.append(self._odr_node(line_id, partner.display_name, line))
            for key in total:
                total[key] += values[key]
        return nodes, total if nodes else False

    @api.model
    def _odr_detail_lines(self, data, options, line, offset, limit):
        partner_id = self._odr_line_id_part(line['id'], 'partner')
        if not partner_id:
            return [], 0
        domain = self._odr_partner_domain(options) + self._odr_period_domain(options) + [
            ('partner_id', '=', partner_id)]
        opening = line.get('opening') if options['initial_balance'] else False
        return self._odr_item_lines(line, domain, opening, 'date, move_name, id', offset, limit)

    @api.model
    def _om_line_action(self, options, line_id):
        partner_id = self._odr_line_id_part(line_id, 'partner')
        if not partner_id:
            return False
        partner = self.env['res.partner'].browse(partner_id)
        domain = self._odr_partner_domain(options) + self._odr_period_domain(options) + [
            ('partner_id', '=', partner_id)]
        return self._odr_journal_items_action(domain, partner.display_name)
