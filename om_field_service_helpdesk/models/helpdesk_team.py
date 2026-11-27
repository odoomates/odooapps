from odoo import fields, models


class OmHelpdeskTeam(models.Model):
    _inherit = 'om.helpdesk.team'

    use_field_service = fields.Boolean(
        string="Field Service", help="The tickets of this team can be planned as field service jobs.")
    fs_project_id = fields.Many2one(
        'project.project', string="Field Service Project", domain="[('is_field_service', '=', True)]",
        help="Project of the jobs made from the tickets. Empty: the first field service project.")
    fs_job_type_id = fields.Many2one('om.fs.job.type', string="Default Job Type")
    fs_auto_create = fields.Boolean(
        string="Create a Job for Each Ticket",
        help="Every new ticket of the team creates a field service job, ready to plan. Without it, jobs "
             "are created from the ticket, or by the ticket types that create jobs.")
    fs_done_message = fields.Selection([
        ('none', "Nothing"),
        ('note', "Internal note with the report"),
        ('customer', "Message to the customer with the report"),
    ], string="When the Job Is Done", default='customer', required=True)
    fs_close_ticket = fields.Boolean(
        string="Close the Ticket When the Job Is Done",
        help="The ticket goes to the closing stage of the team once all its jobs are done or cancelled.")
