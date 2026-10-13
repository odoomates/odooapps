from odoo import SUPERUSER_ID, api


def post_init_hook(cr, registry):
    """ A plan with three reminders for the companies that have none yet """
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['followup.followup']._create_default_plans(env['res.company'].search([]))
