from odoo import fields, models


class OmHelpdeskTicketType(models.Model):
    _inherit = 'om.helpdesk.ticket.type'

    fs_create_job = fields.Boolean(
        string="Creates a Field Service Job",
        help="A new ticket of this type creates a field service job, in the teams that use field service.")
    fs_job_type_id = fields.Many2one('om.fs.job.type', string="Field Service Job Type")
