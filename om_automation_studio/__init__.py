from odoo import SUPERUSER_ID, api

from . import models, wizard


def uninstall_hook(cr, registry):
    """ The automation rules and the Action menu entries made by publishing
    have no XML id: remove them with the module. """
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['om.workflow'].with_context(active_test=False).search([])._remove_triggers()
    env['om.workflow']._sync_run_bindings(keep_models=())
