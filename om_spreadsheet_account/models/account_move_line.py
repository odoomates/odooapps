from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.model
    def om_spreadsheet_fetch_balance(self, args_list):
        """ Balances of the OM.ACCOUNT.BALANCE spreadsheet formula, for the companies selected by the user.

        The input list looks like this::

            [{
                account_types: str[],
                date_from: str or False (from the beginning),
                date_to: str or False (up to now),
                include_unposted: bool,
            }]

        The journal items are grouped by account once per period, then summed by type.
        """
        balances_by_period = {}
        results = []
        for args in args_list:
            date_from = args.get('date_from') or False
            date_to = args.get('date_to') or False
            include_unposted = bool(args.get('include_unposted'))
            period = (date_from, date_to, include_unposted)
            if period not in balances_by_period:
                domain = [
                    ('company_id', 'in', self.env.companies.ids),
                    ('parent_state', '!=', 'cancel') if include_unposted else ('parent_state', '=', 'posted'),
                ]
                if date_from:
                    domain.append(('date', '>=', fields.Date.to_date(date_from)))
                if date_to:
                    domain.append(('date', '<=', fields.Date.to_date(date_to)))
                balances = {}
                for group in self.read_group(domain, ['balance:sum'], ['account_id']):
                    account = self.env['account.account'].browse(group['account_id'][0])
                    balances.setdefault(account.account_type, 0.0)
                    balances[account.account_type] += group['balance']
                balances_by_period[period] = balances
            balances = balances_by_period[period]
            results.append({
                'balance': sum(balances.get(account_type, 0.0) for account_type in args.get('account_types') or []),
            })
        return results
