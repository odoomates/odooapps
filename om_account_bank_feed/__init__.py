from . import controllers
from . import models
from . import wizard


def uninstall_hook(env):
    env['account.journal'].search([('bank_statements_source', '=', 'bank_feed')]).bank_statements_source = 'undefined'
