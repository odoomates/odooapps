from collections import defaultdict

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import SQL
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)


class OmInterCompanyBalanceReport(models.AbstractModel):
    """What each company of the group is owed by the others, as its own books say and as the books of
    the other company say, and the difference between the two.

    A row is the balance of one company with one other group company on one account: on the receivable
    and payable accounts (or only on the accounts flagged inter-company), of the journal items whose
    partner is a group company. The balance of A with B counts as "Our Books" for the pair (A, B) and,
    with the opposite sign, as "Their Books" for the pair (B, A)."""
    _name = 'om.inter.company.balance.report'
    _inherit = 'om.report'
    _description = 'Inter-Company Balances'

    _report_name = 'Inter-Company Balances'
    _report_description = _lt("What each group company owes the others, as both sides book it, and the differences.")
    _report_app = 'accounting'
    _report_section = 'inter_company'
    _report_sequence = 90
    _report_icon = 'swap_horiz'
    _report_group = 'account.group_account_readonly'
    _report_date_mode = 'as_of'
    _report_group_by = ('company', 'partner_company', 'book', 'account')
    _report_default_group_by = ('company', 'partner_company')
    _report_expand_default = True
    _report_rounding = True
    _report_bar_column = 'difference'

    @api.model
    def _om_report_title(self):
        return self.env._("Inter-Company Balances")

    @api.model
    def _om_sections(self):
        return {'inter_company': self.env._("Inter-Company")}

    @api.model
    def _om_name_label(self, options):
        return self.env._("Company")

    @api.model
    def _om_dimensions(self):
        return {
            'company': {'label': self.env._("Company"), 'model': 'res.company', 'icon': 'business'},
            'partner_company': {'label': self.env._("Other Company"), 'model': 'res.company', 'icon': 'handshake'},
            'book': {'label': self.env._("Books"), 'icon': 'book', 'selection': {
                'own': self.env._("Our books"), 'their': self.env._("Their books")}},
            'account': {'label': self.env._("Account"), 'model': 'account.account', 'icon': 'account_tree'},
        }

    @api.model
    def _om_toggles(self):
        return [
            {'key': 'flagged_only', 'label': self.env._("Inter-company accounts only"), 'default': False,
             'help': self.env._("Only the accounts flagged Inter-Company; without it, the receivable and payable "
                                "accounts as well.")},
            {'key': 'hide_zero', 'label': self.env._("Hide settled pairs"), 'default': True,
             'help': self.env._("Leave out the companies whose balances are zero on both sides.")},
        ]

    @api.model
    def _om_choices(self):
        choices = [{'key': 'target_move', 'label': self.env._("Entries"), 'icon': 'check_circle', 'menu': 'bar',
                    'default': 'posted', 'choices': [['posted', self.env._("Posted entries")],
                                                     ['all', self.env._("All entries")]]}]
        currencies = self.env['res.currency'].search([('active', '=', True)], order='name')
        if len(currencies) > 1:
            choices.append({'key': 'presentation_currency', 'label': self.env._("Currency"),
                            'icon': 'attach_money', 'menu': 'bar',
                            'default': str(self.env.company.currency_id.id),
                            'choices': [[str(currency.id), currency.name] for currency in currencies]})
        return choices

    @api.model
    def _om_prepare(self, options):
        currency_id = str(options.get('presentation_currency') or '')
        return self.with_context(om_ic_currency_id=int(currency_id) if currency_id.isdigit() else False)

    @api.model
    def _om_currency(self):
        currency = self.env['res.currency'].browse(self.env.context.get('om_ic_currency_id') or 0).exists()
        return currency or self.env.company.currency_id

    @api.model
    def _om_subtitle(self, options):
        subtitle = super()._om_subtitle(options)
        currency = self._om_currency()
        subtitle = self.env._("%(period)s, in %(currency)s", period=subtitle, currency=currency.name)
        if len(self.env.companies) < 2:
            subtitle += ' - ' + self.env._("select the group companies in the company switcher to see both sides")
        return subtitle

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'own', 'label': self.env._("Our Books"), 'type': 'monetary', 'aggregate': 'sum',
             'optional': False, 'help': self.env._("What the other company owes, as the company books it "
                                                   "(negative: what the company owes).")},
            {'key': 'their', 'label': self.env._("Their Books"), 'type': 'monetary', 'aggregate': 'sum',
             'optional': False, 'help': self.env._("The same, as the other company books it.")},
            {'key': 'difference', 'label': self.env._("Difference"), 'type': 'monetary', 'aggregate': 'sum',
             'optional': False, 'help': self.env._("Our books less their books: zero when both sides agree. A "
                                                   "difference shows on both companies; the total counts it once.")},
        ]

    @api.model
    def _om_get_rows(self, options):
        companies = self.env.companies
        if not companies:
            return []
        conditions = [
            SQL("aml.company_id = ANY(%s)", companies.ids),
            SQL("cp.om_ic_company_id = ANY(%s)", companies.ids),
            SQL("cp.om_ic_company_id != aml.company_id"),
            SQL("aml.date <= %s", options.get('date_to') or fields.Date.context_today(self)),
            SQL("aml.parent_state = 'posted'") if options.get('target_move') != 'all'
            else SQL("aml.parent_state != 'cancel'"),
        ]
        if options.get('flagged_only'):
            conditions.append(SQL("acc.om_inter_company"))
        else:
            conditions.append(SQL(
                "(acc.om_inter_company OR acc.account_type IN ('asset_receivable', 'liability_payable'))"))
        self.env['account.move.line'].flush_model()
        self.env['res.partner'].flush_model(['om_ic_company_id', 'commercial_partner_id'])
        self.env.cr.execute(SQL("""
            SELECT aml.company_id, cp.om_ic_company_id AS partner_company_id, aml.account_id, aml.currency_id,
                   SUM(aml.balance) AS balance, SUM(aml.amount_currency) AS amount_currency
              FROM account_move_line aml
              JOIN account_account acc ON acc.id = aml.account_id
              JOIN res_partner p ON p.id = aml.partner_id
              JOIN res_partner cp ON cp.id = CASE WHEN p.om_ic_company_id IS NOT NULL THEN p.id
                                                  ELSE COALESCE(p.commercial_partner_id, p.id) END
             WHERE %s
          GROUP BY aml.company_id, cp.om_ic_company_id, aml.account_id, aml.currency_id
        """, SQL(" AND ").join(conditions)))
        results = self.env.cr.dictfetchall()
        currency = self._om_currency()
        date = options.get('date_to') or fields.Date.context_today(self)
        Company = self.env['res.company']
        rows = []
        for res in results:
            company = Company.browse(res['company_id'])
            if res['currency_id'] == currency.id:
                amount = res['amount_currency']
            else:
                amount = company.currency_id._convert(res['balance'], currency, company, date, round=False)
            if currency.is_zero(amount):
                continue
            rows.append({'company_id': res['company_id'], 'partner_company_id': res['partner_company_id'],
                         'book_id': 'own', 'account_id': res['account_id'],
                         'own': amount, 'their': 0.0, 'difference': amount})
            rows.append({'company_id': res['partner_company_id'], 'partner_company_id': res['company_id'],
                         'book_id': 'their', 'account_id': res['account_id'],
                         'own': 0.0, 'their': -amount, 'difference': amount})
        return rows

    @api.model
    def _om_filter_rows(self, rows, options, columns):
        if options.get('hide_zero'):
            # a pair is settled when both sides net to zero
            currency = self._om_currency()
            nets = defaultdict(lambda: [0.0, 0.0])
            for row in rows:
                key = (row['company_id'], row['partner_company_id'])
                nets[key][0] += row['own']
                nets[key][1] += row['their']
            open_pairs = {key for key, (own, their) in nets.items()
                          if not (currency.is_zero(own) and currency.is_zero(their))}
            rows = [row for row in rows if (row['company_id'], row['partner_company_id']) in open_pairs]
        if options.get('kpi_filter'):
            rows = self._om_kpi_filter_rows(rows, options['kpi_filter'], options)
        return rows

    @api.model
    def _om_finalize_node(self, node, options):
        super()._om_finalize_node(node, options)
        if node['id'] == 'total':
            # a difference shows on both companies of the pair: the total counts it once
            node['values']['difference'] = node['values'].get('difference', 0.0) / 2

    @api.model
    def _om_differences(self, rows):
        """{(company, other company): difference} of the pairs whose sides do not agree."""
        currency = self._om_currency()
        totals = defaultdict(float)
        for row in rows:
            totals[(row['company_id'], row['partner_company_id'])] += row['difference']
        return {key: value for key, value in totals.items() if not currency.is_zero(value)}

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi == 'differences':
            pairs = self._om_differences(rows)
            return [row for row in rows if (row['company_id'], row['partner_company_id']) in pairs]
        return rows

    @api.model
    def _om_get_kpis(self, data, options):
        rows = data['all_rows']
        differences = self._om_differences(rows)
        pairs = {frozenset(key) for key in differences}
        owed = defaultdict(float)
        for row in rows:
            owed[(row['company_id'], row['partner_company_id'])] += row['own']
        receivable = sum(value for value in owed.values() if value > 0)
        return [
            {'key': 'owed', 'label': self.env._("Owed within the group"), 'value': receivable, 'type': 'monetary',
             'icon': 'payments'},
            {'key': 'companies', 'label': self.env._("Companies with balances"),
             'value': len({key[0] for key, value in owed.items() if value}), 'type': 'int', 'icon': 'business'},
            {'key': 'differences', 'label': self.env._("Pairs with a difference"), 'value': len(pairs),
             'type': 'int', 'icon': 'warning', 'tone': 'danger' if pairs else 'success', 'filter': 'differences'},
            {'key': 'difference', 'label': self.env._("Total difference"),
             'value': sum(abs(value) for value in differences.values()) / 2, 'type': 'monetary',
             'icon': 'balance', 'tone': 'danger' if pairs else 'success'},
        ]

    # ------------------------------------------------------------------
    # Journal items behind a line
    # ------------------------------------------------------------------

    @api.model
    def _om_node_line(self, node, options):
        line = super()._om_node_line(node, options)
        # a line opens the journal items of both books, not the company
        line['open'] = False
        line['drill'] = True
        return line

    @api.model
    def _om_line_part(self, line_id, prefix):
        for part in (line_id or '').split('|'):
            key, _sep, value = part.rpartition('-')
            if key == prefix:
                return value
        return False

    @api.model
    def _om_line_action(self, options, line_id):
        company_id = self._om_line_part(line_id, 'company')
        other_id = self._om_line_part(line_id, 'partner_company')
        book = self._om_line_part(line_id, 'book')
        account_id = self._om_line_part(line_id, 'account')
        companies = self.env.companies.ids
        pairs = []
        for mine, theirs, side in ((company_id, other_id, 'own'), (other_id, company_id, 'their')):
            if book and book != side:
                continue
            mine_ids = [int(mine)] if mine and mine.isdigit() else companies
            theirs_ids = [int(theirs)] if theirs and theirs.isdigit() else companies
            pairs.append(Domain('company_id', 'in', mine_ids) & (
                Domain('partner_id.om_ic_company_id', 'in', theirs_ids) | (
                    Domain('partner_id.om_ic_company_id', '=', False)
                    & Domain('partner_id.commercial_partner_id.om_ic_company_id', 'in', theirs_ids))))
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_account_moves_all')
        action.update({
            'name': self.env._("Inter-Company Journal Items"),
            'domain': self._om_aml_domain(options, pairs, account_id),
            'context': {'create': False, 'search_default_group_by_move': 0},
            'target': 'current',
        })
        action.pop('path', None)
        return action

    @api.model
    def _om_aml_domain(self, options, pairs, account_id):
        sides = Domain.OR(pairs)
        domain = sides & Domain('date', '<=', options.get('date_to') or fields.Date.context_today(self))
        if options.get('target_move') != 'all':
            domain &= Domain('parent_state', '=', 'posted')
        else:
            domain &= Domain('parent_state', '!=', 'cancel')
        if options.get('flagged_only'):
            domain &= Domain('account_id.om_inter_company', '=', True)
        else:
            domain &= Domain('account_id.om_inter_company', '=', True) | Domain(
                'account_id.account_type', 'in', ('asset_receivable', 'liability_payable'))
        if account_id and account_id.isdigit():
            domain &= Domain('account_id', '=', int(account_id))
        return list(domain)
