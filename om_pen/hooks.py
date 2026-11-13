def uninstall_hook(env):
    """ Take the generated views away with the module.

    They are filed under an external id of a module that is never installed, so
    uninstalling would otherwise leave them in place, still changing the views they
    extend, with nothing left to switch them off. Custom fields stay: they hold data.
    """
    customizations = env['om.pen.view'].sudo().with_context(active_test=False).search([])
    customizations.custom_view_id.unlink()
