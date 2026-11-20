from collections import defaultdict

from odoo import api, models, _
from odoo import _lt


AMOUNTS = ('balance', 'revalued', 'adjustment')


class OmDynamicReportRevaluation(models.AbstractModel):
    """Unrealized Currency Gains/Losses: what is open in a foreign currency at a
    date, per currency, account and partner: the amount in the currency, in the
    books, at the closing rate of the date, and the difference, which is the
    unrealized gain or loss. The figures are those of the currency revaluation,
    which posts the adjustment entry from a currency of the report.
    """
    _name = 'om.dynamic.report.revaluation'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Unrealized Currency Gains/Losses'

    _report_name = 'Unrealized Currency Gains/Losses'
    _report_description = _lt("Open foreign currency balances at the closing rate, and the unrealized gain or loss.")
    _report_section = 'statements'
    _report_sequence = 12
    _report_icon = 'currency_exchange'
    _report_date_mode = 'as_of'
    _report_default_preset = 'today'

    @api.model
    def _om_report_title(self):
        return _("Unrealized Currency Gains/Losses")

    @api.model
    def _om_name_label(self, options):
        return _("Currency / Account / Partner")

    @api.model
    def _om_filters(self):
        return [{'key': 'currency_ids', 'label': _("Currencies"), 'model': 'res.currency',
                 'icon': 'currency_exchange', 'domain': [['id', '!=', self.env.company.currency_id.id]]}]

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'amount_currency', 'label': _("Open Amount"), 'type': 'float',
             'help': _("What is open in the currency.")},
            {'key': 'balance', 'label': _("In the Books"), 'type': 'monetary'},
            {'key': 'revalued', 'label': _("At the Closing Rate"), 'type': 'monetary'},
            {'key': 'adjustment', 'label': _("Unrealized Gain/Loss"), 'type': 'monetary', 'drill': True,
             'help': _("The difference: a gain when positive, a loss when negative.")},
        ]

    @api.model
    def _odr_revaluation(self, options, currencies=None):
        """The currency revaluation of the date, not saved: its lines are computed by the revaluation itself."""
        return self.env['currency.revaluation'].new({
            'company_id': self.env.company.id,
            'date': options['date_to'],
            'currency_ids': [(6, 0, (currencies or self.env['res.currency'].browse(
                options.get('currency_ids') or [])).ids)],
        })

    @api.model
    def _odr_tree(self, options):
        values = self._odr_revaluation(options)._get_revaluation_values()
        by_currency = defaultdict(list)
        for value in values:
            by_currency[value['currency_id']].append(value)
        Account = self.env['account.account']
        Partner = self.env['res.partner']
        tree = []
        total = dict.fromkeys(AMOUNTS, 0.0)
        for currency in self.env['res.currency'].browse(list(by_currency)).sorted('name'):
            currency_id = 'currency-%s' % currency.id
            children = []
            sums = dict.fromkeys(AMOUNTS, 0.0)
            amount_currency = 0.0
            for value in by_currency[currency.id]:
                account, partner = Account.browse(value['account_id']), Partner.browse(value['partner_id'] or [])
                node_id = '%s|account-%s|partner-%s' % (currency_id, account.id, partner.id or 0)
                name = account.display_name + (' - %s' % partner.display_name if partner else '')
                line_values = {key: value[key] for key in AMOUNTS}
                line_values['amount_currency'] = value['amount_currency']
                children.append(self._odr_node(node_id, name, self._om_line(
                    node_id, name, line_values, parent_id=currency_id, level=1, kind='leaf', drill=True)))
                for key in AMOUNTS:
                    sums[key] += value[key]
                amount_currency += value['amount_currency']
            for key in AMOUNTS:
                total[key] += sums[key]
            line = self._om_line(
                currency_id, currency.name, {**sums, 'amount_currency': amount_currency}, kind='group',
                has_children=True, count=len(children), unfolded=True,
                actions=[{'key': 'revalue', 'label': _("Post the adjustment"), 'icon': 'publish'}])
            tree.append(self._odr_node(currency_id, currency.name, line, children))
        return tree, total if tree else False

    @api.model
    def _om_total(self, data, options):
        if not data.get('total'):
            return False
        return self._om_line('total', _("Total"), data['total'], kind='total')

    @api.model
    def _om_line_button(self, options, line_id, key):
        """The currency revaluation of the date for the currency of the line, to check and post."""
        currency_id = self._odr_line_id_part(line_id, 'currency')
        if key != 'revalue' or not currency_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _("Currency Revaluation"),
            'res_model': 'currency.revaluation',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_date': options['date_to'], 'default_currency_ids': [currency_id]},
        }

    @api.model
    def _om_cell_action(self, options, line_id, column_key):
        """The open journal items in the currency on the account (and of the partner) of the line."""
        currency_id = self._odr_line_id_part(line_id, 'currency')
        account_id = self._odr_line_id_part(line_id, 'account')
        if not currency_id:
            return False
        revaluation = self._odr_revaluation(options, self.env['res.currency'].browse(currency_id))
        domain = revaluation._revaluation_domain() + [('currency_id', '=', currency_id)]
        if account_id:
            domain.append(('account_id', '=', account_id))
            partner_id = self._odr_line_id_part(line_id, 'partner')
            account = self.env['account.account'].browse(account_id)
            if account.account_type in ('asset_receivable', 'liability_payable'):
                domain += [('partner_id', '=', partner_id or False), ('reconciled', '=', False)]
        return self._odr_journal_items_action(domain, _("Open items in the currency"))
