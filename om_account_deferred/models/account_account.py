from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountAccount(models.Model):
    _inherit = 'account.account'

    om_is_deferred = fields.Boolean(
        string='Own Deferral Account',
        help="Park the deferred amounts of this income or expense account on an account of its own, instead of "
             "the deferral account of the settings: e.g. prepaid insurance apart from the other prepaid expenses.")
    om_deferred_account_id = fields.Many2one(
        'account.account', string='Deferral Account', domain="[('deprecated', '=', False), ('id', '!=', id)]",
        help="Balance sheet account holding what this account defers.")

    @api.constrains('om_is_deferred', 'om_deferred_account_id')
    def _check_om_deferred_account(self):
        for account in self:
            if account.om_is_deferred and not account.om_deferred_account_id:
                raise ValidationError(_("Choose the deferral account of %s.", account.display_name))
            if account.om_deferred_account_id and account.om_deferred_account_id.internal_group in ('income', 'expense'):
                raise ValidationError(_("The deferral account of %s must be a balance sheet account.",
                                        account.display_name))

    def _om_own_deferral_account(self):
        """ The deferral account of this account, when it has one of its own. """
        self.ensure_one()
        return self.om_deferred_account_id if self.om_is_deferred else self.env['account.account']
