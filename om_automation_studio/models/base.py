from odoo import models


class Base(models.AbstractModel):
    """ A record a pending approval blocks keeps the fields the approval
    locks until it is answered. The workflows themselves change it freely. """
    _inherit = 'base'

    def write(self, vals):
        if not self.env.su and self._name in self.env['om.workflow.approval']._locked_models():
            self.env['om.workflow.approval']._check_lock(self, vals)
        return super().write(vals)
