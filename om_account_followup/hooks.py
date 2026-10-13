def post_init_hook(env):
    """ A plan with three reminders for the companies that have none yet """
    env['followup.followup']._create_default_plans(env['res.company'].search([]))
