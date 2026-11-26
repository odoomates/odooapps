from markupsafe import Markup

from odoo import fields, models
from odoo.exceptions import UserError


class OmReleaseForceWizard(models.TransientModel):
    _name = 'om.release.force.wizard'
    _description = 'Force the Release to Pay of Vendor Bills'

    move_ids = fields.Many2many('account.move', string='Vendor Bills', required=True)
    decision = fields.Selection(
        [('yes', 'Release to pay (Yes)'), ('no', 'Hold the payment (No)'), ('auto', 'Back to automatic')],
        string='Release to Pay', required=True, default='yes')
    reason = fields.Text(required=True)

    def action_confirm(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(self.env._('Only an accounting administrator can force the Release to Pay.'))
        bills = self.move_ids.filtered(lambda move: move.move_type == 'in_invoice')
        decision = self.decision
        bills.write({
            'om_release_forced': False if decision == 'auto' else decision,
            'om_release_reason': False if decision == 'auto' else self.reason,
        })
        label = dict(self._fields['decision']._description_selection(self.env))[decision]
        for bill in bills:
            bill.message_post(body=Markup('<b>%s</b>: %s<br/>%s: %s') % (
                self.env._('Release to Pay'), label, self.env._('Reason'), self.reason))
        return {'type': 'ir.actions.act_window_close'}
