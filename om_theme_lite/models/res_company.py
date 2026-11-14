from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_home_background = fields.Image(
        string='Home screen background',
        max_width=2560,
        max_height=1600,
        help="Shown behind the app launcher and on the login page.",
    )
    om_favicon = fields.Image(
        string='Favicon',
        max_width=256,
        max_height=256,
        help="The small icon in the browser tab.",
    )
