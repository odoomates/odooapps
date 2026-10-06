import ast
from odoo import api, models, fields
from odoo.osv import expression


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model
    def _branch_ids(self, company_id):
        """ The company and the branches it consolidates, as ids. """
        return self.env['res.company'].sudo().search([('id', 'child_of', company_id)]).ids

    @api.model
    def _query_get(self, domain=None):
        self.check_access('read')

        context = dict(self._context or {})
        domain = domain or []
        if not isinstance(domain, (list, tuple)):
            domain = ast.literal_eval(domain)

        date_field = 'date'
        if context.get('aged_balance'):
            date_field = 'date_maturity'
        if context.get('date_to'):
            domain += [(date_field, '<=', context['date_to'])]
        if context.get('date_from'):
            if not context.get('strict_range'):
                domain += ['|', (date_field, '>=', context['date_from']), ('account_id.include_initial_balance', '=', True)]
            elif context.get('initial_bal'):
                domain += [(date_field, '<', context['date_from'])]
            else:
                domain += [(date_field, '>=', context['date_from'])]

        if context.get('journal_ids'):
            domain += [('journal_id', 'in', context['journal_ids'])]

        state = context.get('state')
        if state and state.lower() != 'all':
            domain += [('parent_state', '=', state)]
        else:
            # "All Entries" are the draft and posted ones: cancelled entries never count
            domain += [('parent_state', '!=', 'cancel')]

        # a branch posts its entries in its own company, and they belong to the report of the
        # parent that consolidates it. The ids are resolved here instead of with a 'child_of'
        # leaf: the reports splice this WHERE clause into a FROM clause of their own, where the
        # join such a leaf needs has no alias.
        if context.get('company_id'):
            domain += [('company_id', 'in', self._branch_ids(context['company_id']))]
        elif context.get('allowed_company_ids'):
            domain += [('company_id', 'in', self.env.companies.ids)]
        else:
            domain += [('company_id', 'in', self._branch_ids(self.env.company.id))]

        if context.get('reconcile_date'):
            domain += ['|', ('reconciled', '=', False), '|', ('matched_debit_ids.max_date', '>', context['reconcile_date']), ('matched_credit_ids.max_date', '>', context['reconcile_date'])]

        if context.get('account_tag_ids'):
            domain += [('account_id.tag_ids', 'in', context['account_tag_ids'].ids)]

        if context.get('account_ids'):
            domain += [('account_id', 'in', context['account_ids'].ids)]

        if context.get('analytic_tag_ids'):
            domain += [('analytic_tag_ids', 'in', context['analytic_tag_ids'].ids)]

        if context.get('analytic_account_ids'):
            domain += [('analytic_distribution', 'in', context['analytic_account_ids'].ids)]

        if context.get('partner_ids'):
            domain += [('partner_id', 'in', context['partner_ids'].ids)]

        if context.get('partner_categories'):
            domain += [('partner_id.category_id', 'in', context['partner_categories'].ids)]

        where_clause = ""
        where_clause_params = []
        tables = ''
        if domain:
            domain.append(('display_type', 'not in', ('line_section', 'line_note')))
            domain.append(('parent_state', '!=', 'cancel'))
            if context.get('tax_exigible'):
                # the tax report: a cash basis tax is due when it is paid, on its cash basis entry
                domain = expression.AND([domain, self._get_tax_exigible_domain()])

            query = self._where_calc(domain)
            self._apply_ir_rules(query)
            from_string, from_params = query.from_clause
            where_string, where_params = query.where_clause
            tables, where_clause, where_clause_params = from_string, where_string, from_params + where_params
        return tables, where_clause, where_clause_params

    def format_analytic_distribution(self, distribution):
        """ Render an analytic distribution as "Account A, Account B: 40.0%" lines.

        The keys of the distribution hold one id per analytic plan, comma
        separated, so a single entry may name several accounts.
        """
        self.ensure_one()
        if not distribution:
            return []
        result = []
        for key, percentage in distribution.items():
            accounts = self.env["account.analytic.account"].browse(
                int(account_id) for account_id in key.split(",")
            ).exists()
            if not accounts:
                continue
            names = [
                "%s - %s" % (account.name, account.partner_id.name) if account.partner_id else account.name
                for account in accounts
            ]
            result.append("%s: %s%%" % (", ".join(names), percentage))
        return result
