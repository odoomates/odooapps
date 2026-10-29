from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    academy_welcomed = fields.Boolean(help="The learner went through the welcome guide of the Academy.")
    academy_warmup = fields.Json(help="The warm-up of the Academy: answers, tasks done, and what was there at the start.")
