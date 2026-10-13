from odoo import models

CHECK_REPORTS = ('om_account_check_printing.report_check', 'om_account_check_printing.report_check_test')


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def get_paperformat(self):
        # the paper of the cheques is the one of their format
        format_id = self.env.context.get('om_check_format_id')
        if format_id and self.report_name in CHECK_REPORTS:
            check_format = self.env['account.check.format'].sudo().browse(format_id).exists()
            if check_format.paperformat_id:
                return check_format.paperformat_id
        return super().get_paperformat()
