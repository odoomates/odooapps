from odoo import SUPERUSER_ID, api

from .models.res_users import LAUNCHER_ACTION


def post_init_hook(cr, registry):
    """Land existing users on the launcher.

    Only users who have not chosen a home action of their own are moved, so nobody's
    preference is overwritten by installing a theme.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    action = env.ref(LAUNCHER_ACTION, raise_if_not_found=False)
    if not action:
        return
    users = env['res.users'].sudo().search([('share', '=', False), ('action_id', '=', False)])
    users.write({'action_id': action.id})


def uninstall_hook(cr, registry):
    """Hand the home screen back.

    Without this every user we pointed at the launcher would be left with a home
    action that no longer exists.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    action = env.ref(LAUNCHER_ACTION, raise_if_not_found=False)
    if not action:
        return
    users = env['res.users'].sudo().search([('action_id', '=', action.id)])
    users.write({'action_id': False})
