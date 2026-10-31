from odoo import models


class AccountLoanOperation(models.Model):
    _inherit = 'account.loan.operation'

    def action_cancel(self):
        """ Cancel the right-of-use asset with the recognition of its lease. """
        recognitions = self.filtered(lambda op: op.state == 'posted' and op.operation_type == 'recognition')
        leases = recognitions.loan_id.filtered('asset_id')
        res = super().action_cancel()
        for lease in leases:
            asset = lease.asset_id
            if asset.state == 'draft':
                asset.unlink()
            elif asset.state != 'cancelled':
                asset.set_to_cancelled()
            lease.asset_id = False
        return res
