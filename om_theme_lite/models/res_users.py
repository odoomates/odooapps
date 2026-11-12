from odoo import api, fields, models

LAUNCHER_ACTION = 'om_theme_lite.action_app_launcher'


class ResUsers(models.Model):
    _inherit = 'res.users'

    om_color_scheme = fields.Selection(
        [('light', 'Light'), ('dark', 'Dark'), ('system', 'System')],
        string='Colour scheme',
        default='light',
        required=True,
        # the choice is the user's own, so they may set it without write access
        # on res.users
        user_writeable=True,
        help="Dark renders the backend on dark surfaces; System follows the light or dark "
             "setting of the device. It applies to this user only.",
    )
    om_sidebar_type = fields.Selection(
        [('none', 'Hidden'), ('icons', 'Icons'), ('large', 'Icons and names')],
        string='Apps sidebar',
        default='none',
        required=True,
        user_writeable=True,
        help="A column of app icons down the left side of the screen.",
    )
    om_chatter_position = fields.Selection(
        [('auto', 'Automatic'), ('bottom', 'Below the form')],
        string='Chatter position',
        default='auto',
        required=True,
        user_writeable=True,
        help="Automatic puts the chatter beside the form on wide screens and below it "
             "on narrow ones; Below the form always keeps it underneath.",
    )
    om_dialog_size = fields.Selection(
        [('normal', 'Normal'), ('full', 'Full screen')],
        string='Dialog size',
        default='normal',
        required=True,
        user_writeable=True,
        help="The size pop-up windows open in. Each one can still be resized from its header.",
    )
    om_app_order = fields.Json(
        string='App order',
        # set by dragging the tiles on the home screen, so the user's own to change
        user_writeable=True,
        copy=False,
        help="The apps on the home screen, in the order this user dragged them into.",
    )

    @api.model
    def _om_launcher_action(self):
        return self.env.ref(LAUNCHER_ACTION, raise_if_not_found=False)

    @api.model
    def _om_default_action_id(self):
        """New users land on the launcher."""
        action = self._om_launcher_action()
        return action.id if action else False

    action_id = fields.Many2one(default=lambda self: self._om_default_action_id())

    @api.model_create_multi
    def create(self, vals_list):
        """Give the launcher to internal users only.

        The default above cannot tell yet whether the new user is a portal one, so
        portal and public users are put back on no home action once they exist.
        """
        users = super().create(vals_list)
        launcher = self._om_launcher_action()
        if launcher:
            users.filtered(lambda u: u.share and u.action_id.id == launcher.id).action_id = False
        return users
