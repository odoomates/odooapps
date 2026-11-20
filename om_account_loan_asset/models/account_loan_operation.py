from odoo import models
from odoo.exceptions import UserError


class AccountLoanOperation(models.Model):
    _inherit = 'account.loan.operation'

    def action_cancel(self):
        """ Delete the right-of-use asset with the recognition of its lease, as long as it has no
        depreciation entry. """
        recognitions = self.filtered(lambda op: op.state == 'posted' and op.operation_type == 'recognition')
        leases = recognitions.loan_id.filtered('asset_id')
        for lease in leases:
            if lease.asset_id.depreciation_line_ids.filtered('move_id'):
                raise UserError(self.env._(
                    'The right-of-use asset %(asset)s of %(lease)s has depreciation entries: delete them first.',
                    asset=lease.asset_id.display_name, lease=lease.display_name))
        res = super().action_cancel()
        for lease in leases:
            asset = lease.asset_id
            lease.asset_id = False
            asset.set_to_draft()
            asset.unlink()
        return res
