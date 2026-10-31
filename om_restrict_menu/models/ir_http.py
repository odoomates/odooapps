from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """ A Home Action opening only from hidden menus would open what the user is not meant to see: the web
        client opens the first visible app instead. """
        info = super().session_info()
        if info.get('home_action_id'):
            Menu = self.env['ir.ui.menu']
            if Menu._om_action_hidden(self.env.user.sudo().action_id, Menu._om_hidden_menu_ids()):
                info['home_action_id'] = False
        return info
