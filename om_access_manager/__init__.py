from . import models
from . import wizard
from . import controllers


def uninstall_hook(env):
    # The hidden group of a profile carries its users and implies the groups the
    # profile grants: left behind, it would go on granting them with nothing
    # restricting them any more. Removing the profiles removes their groups.
    env['om.access.profile'].with_context(active_test=False).search([]).unlink()
