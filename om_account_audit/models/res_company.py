from odoo import fields, models
from odoo.exceptions import UserError

SECURED_TYPES = ('sale', 'purchase', 'general')


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_audit_weekly_check = fields.Boolean(
        string='Weekly Integrity Check', default=True,
        help='Check the data inalterability of the company every week, and keep the result.')
    om_audit_secure_on_close = fields.Boolean(
        string='Secure Entries on Closing',
        help='When a period is closed, its posted entries are secured: they can never be changed again.')

    def action_om_secure_all_journals(self):
        """ The sales, purchase and miscellaneous journals secure their entries as soon as they are posted. """
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(self.env._('Only the accounting administrators secure the journals.'))
        journals = self.env['account.journal'].search([
            *self.env['account.journal']._check_company_domain(self),
            ('type', 'in', SECURED_TYPES), ('restrict_mode_hash_table', '=', False),
        ])
        journals.restrict_mode_hash_table = True
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': self.env._('%s journals now secure their posted entries.', len(journals))
                if journals else self.env._('All the sales, purchase and miscellaneous journals are secured.'),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
