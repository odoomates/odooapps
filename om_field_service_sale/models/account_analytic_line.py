from odoo import models


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    def _timesheet_determine_sale_line(self):
        """ The time of a covered job is not billed, nor the travel when its job type says so. """
        task = self.task_id
        if task.is_field_service:
            if task.is_covered:
                return False
            if self.fs_time_type == 'travel' and task.job_type_id and not task.job_type_id.bill_travel:
                return False
        return super()._timesheet_determine_sale_line()
