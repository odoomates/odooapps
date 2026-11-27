from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    fs_request_review = fields.Boolean(
        string="Review Online Requests",
        help="Service requests sent from the website wait for a dispatcher to accept them before they are "
             "offered for planning.")
    fs_request_project_id = fields.Many2one(
        'project.project', string="Project of Online Requests", domain="[('is_field_service', '=', True)]",
        help="Field service project of the jobs requested on the website. Empty: the first field service "
             "project.")
