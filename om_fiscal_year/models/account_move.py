from odoo import api, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _check_not_fiscal_year_closing(self):
        closed_years = self.env['account.fiscal.year'].sudo().search([('closing_move_id', 'in', self.ids)])
        if closed_years:
            raise UserError(_(
                'This entry closes the fiscal year %s. Reopen the fiscal year instead of changing it.',
                ', '.join(closed_years.mapped('name'))))

    def button_draft(self):
        self._check_not_fiscal_year_closing()
        return super().button_draft()

    def button_cancel(self):
        self._check_not_fiscal_year_closing()
        return super().button_cancel()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_fiscal_year_closing(self):
        self._check_not_fiscal_year_closing()
