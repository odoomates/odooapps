from . import models


def post_init_hook(env):
    """ Existing equipment gets its planning resource, scheduled requests their slot. """
    equipment = env['maintenance.equipment'].with_context(active_test=False).search([])
    equipment._planning_ensure_resource()
    requests = env['maintenance.request'].search([
        ('schedule_date', '!=', False),
        ('schedule_end', '!=', False),
        ('state', 'not in', ('done', 'cancelled')),
    ])
    requests._planning_mnt_sync_slots()
