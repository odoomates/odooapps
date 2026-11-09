from odoo import SUPERUSER_ID, Command, api


def migrate(cr, version):
    """ The app has its own groups now: the administrators of Odoo are no
    longer its supervisors through their group. """
    env = api.Environment(cr, SUPERUSER_ID, {})
    system = env.ref('base.group_system')
    supervisor = env.ref('om_automation_studio.om_automation_studio_group_supervisor')
    if supervisor in system.implied_ids:
        system.implied_ids = [Command.unlink(supervisor.id)]
