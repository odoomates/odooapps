from .models.res_users import LAUNCHER_ACTION


def post_init_hook(env):
    """Land existing users on the launcher.

    Only users who have not chosen a home action of their own are moved, so nobody's
    preference is overwritten by installing a theme.
    """
    action = env.ref(LAUNCHER_ACTION, raise_if_not_found=False)
    if not action:
        return
    users = env['res.users'].sudo().search([('share', '=', False), ('action_id', '=', False)])
    users.write({'action_id': action.id})


def uninstall_hook(env):
    """Hand the home screen back.

    Without this every user we pointed at the launcher would be left with a home
    action that no longer exists.
    """
    action = env.ref(LAUNCHER_ACTION, raise_if_not_found=False)
    if not action:
        return
    users = env['res.users'].sudo().search([('action_id', '=', action.id)])
    users.write({'action_id': False})
