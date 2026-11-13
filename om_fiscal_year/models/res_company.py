from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    retained_earnings_account_id = fields.Many2one(
        'account.account', string='Retained Earnings Account', check_company=True,
        domain=[('account_type', '=', 'equity')],
        help='Account receiving the earnings of the fiscal years when they are closed.')

    def _get_unreconciled_statement_lines_redirect_action(self, unreconciled_statement_lines):
        """ The action of the warning shown when a period with unreconciled bank transactions is locked. Core gives
        it no views, which the web client needs to open it from the warning: they are the views of its mode. """
        action = super()._get_unreconciled_statement_lines_redirect_action(unreconciled_statement_lines)
        if not action.get('views'):
            action['views'] = [(False, mode) for mode in action['view_mode'].split(',')]
        return action
