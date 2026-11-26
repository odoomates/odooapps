from odoo import fields, models

from .res_company import SALTEDGE_CREDENTIAL_GROUPS


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    saltedge_app_id = fields.Char(related='company_id.saltedge_app_id', readonly=False,
                                  groups=SALTEDGE_CREDENTIAL_GROUPS)
    saltedge_secret = fields.Char(related='company_id.saltedge_secret', readonly=False,
                                  groups=SALTEDGE_CREDENTIAL_GROUPS)
    saltedge_private_key = fields.Char(related='company_id.saltedge_private_key', readonly=False,
                                       groups=SALTEDGE_CREDENTIAL_GROUPS)
    saltedge_include_fake = fields.Boolean(related='company_id.saltedge_include_fake', readonly=False,
                                           groups=SALTEDGE_CREDENTIAL_GROUPS)
    saltedge_customer_id = fields.Char(related='company_id.saltedge_customer_id',
                                       groups=SALTEDGE_CREDENTIAL_GROUPS)

    def action_saltedge_test(self):
        """ Check the credentials with a request listing the connections of the customer, or the countries
        when no customer exists yet """
        self.ensure_one()
        self.env['bank.feed.connection']._saltedge_api(self.company_id).request('GET', '/countries')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': 'success', 'message': self.env._('Salt Edge accepted the credentials.')},
        }
