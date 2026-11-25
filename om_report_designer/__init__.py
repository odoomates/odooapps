from . import models


def uninstall_hook(env):
    """ The reports, templates, paper formats and menus made by publishing
    have no XML id: remove them with the module. """
    env['om.report.design'].with_context(active_test=False).search([])._unpublish()
