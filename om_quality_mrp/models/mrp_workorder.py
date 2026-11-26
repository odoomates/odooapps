from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain


class MrpWorkorder(models.Model):
    _name = 'mrp.workorder'
    _inherit = ['mrp.workorder', 'om.quality.document.mixin']

    om_quality_check_ids = fields.One2many('om.quality.check', 'workorder_id', string='Quality Check Records')

    def _om_quality_check_domain(self):
        return Domain('workorder_id', 'in', self.ids)

    def _om_quality_document_of_check(self, check):
        return check.workorder_id

    def button_finish(self):
        blocking = self._om_quality_blocking_checks()
        if blocking:
            raise UserError(self.env._(
                "The work order %(workorder)s waits for its quality checks: %(checks)s. Record them from the "
                "Quality Checks button of the step, or ask a quality manager to override them.",
                workorder=', '.join(blocking.workorder_id.mapped('name')),
                checks=', '.join(blocking.mapped('display_name'))))
        return super().button_finish()
