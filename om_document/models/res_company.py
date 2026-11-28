from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_documents_share_days = fields.Integer(
        string='Share Links Valid For', default=30,
        help='The days a new share link is valid for. 0 for links that never expire.')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_documents_share_days = fields.Integer(related='company_id.om_documents_share_days', readonly=False)
