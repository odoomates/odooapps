from odoo import models
from odoo.http import request

from . import simulation

SESSION_KEY = 'flow_visualizer'


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        if self.env.uid and self.env.user.has_group('base.group_system'):
            result['flow_visualizer'] = {
                'enabled': bool(request and request.session.get(SESSION_KEY)),
                'simulation': bool(simulation.current(self.env.cr.dbname)),
            }
        return result
