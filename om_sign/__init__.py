from odoo.exceptions import UserError

from . import controllers
from . import models
from . import wizard


def pre_init_hook(env):
    """ Sign of Odoo Enterprise makes the same models: the two are not installed together. """
    if env['ir.module.module'].search_count([('name', '=', 'sign'), ('state', 'in', ('installed', 'to upgrade'))]):
        raise UserError(env._('Uninstall the Sign app of Odoo Enterprise before installing this one.'))
