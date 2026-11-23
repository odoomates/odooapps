from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    om_chatter_position = fields.Selection(
        [('auto', 'Automatic'), ('bottom', 'Below the form'), ('side', 'Beside the form')],
        string='Chatter position',
        default='auto',
        required=True,
        # the choice is the user's own, so they may set it without write access
        # on res.users
        user_writeable=True,
        help="Automatic puts the chatter beside the form on wide screens and below it "
             "on narrow ones; Below the form always keeps it underneath; Beside the form "
             "keeps it next to the form on every screen but a phone or a small tablet.",
    )
