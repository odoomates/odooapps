# The tests see no module of the learner on disk, whatever is in the addons path
# of the machine running them: a folder learn_library of one's own would
# otherwise be found, and change what the Academy does.
import os
from unittest.mock import patch

TARGETS = ('odoo.addons.om_academy.models.academy_progress.get_module_path',
           'odoo.addons.om_academy.models.live_builder.get_module_path')


def modules_on_disk(case, folder=None):
    """ Odoo finds the learner's modules only in ``folder`` (none by default). """
    def find(name, **kwargs):
        path = os.path.join(folder, name) if folder else None
        return path if path and os.path.isdir(path) else False
    for target in TARGETS:
        patcher = patch(target, find)
        patcher.start()
        case.addCleanup(patcher.stop)


def named_learner(case, name='Test Learner'):
    """ The learner wrote their name, which the Academy asks before building. """
    case.env['ir.default'].set('academy.progress', 'author_name', name)
    case.env['academy.progress'].search([('author_name', '=', False)]).author_name = name
