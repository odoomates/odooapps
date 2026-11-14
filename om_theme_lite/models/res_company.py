from odoo import api, fields, models


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
    om_uses_default_logo = fields.Boolean(
        compute='_compute_om_uses_default_logo',
        help="The company still has the logo Odoo ships, so the login page shows none.",
    )

    @api.depends('logo')
    def _compute_om_uses_default_logo(self):
        default_logo = self._get_logo()
        for company in self:
            company.om_uses_default_logo = not company.logo or company.logo == default_logo
