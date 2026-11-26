from . import controllers
from . import models


def _post_init_hook(env):
    env['res.users'].search([('share', '=', False)])._om_ai_ensure_chat()
