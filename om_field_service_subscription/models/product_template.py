from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    fs_maintenance = fields.Boolean(
        string="Maintenance Visits",
        help="A subscription with this product creates field service jobs for its maintenance visits.")
    fs_job_interval = fields.Integer(
        string="Visit Every", default=1,
        help="Number of periods of the recurring plan between two visits: 1 for a visit every period.")
    fs_lead_days = fields.Integer(
        string="Create Days Before", default=14,
        help="The job of a visit is created this many days before it is due, to be planned in time.")
    fs_job_type_id = fields.Many2one(
        'om.fs.job.type', string="Visit Job Type",
        help="Job type of the visits: duration, checklist (worksheet) and instructions.")
    fs_technician_id = fields.Many2one(
        'hr.employee', string="Preferred Technician", domain="[('is_technician', '=', True)]",
        help="Technician of the visits, unless the subscription names another one.")
    fs_coverage = fields.Selection([
        ('none', "Not covered: billed"),
        ('contract', "Visits of the contract covered"),
        ('all', "Every job of the customer covered"),
    ], string="Field Service Coverage", default='contract', required=True,
        help="Covered jobs are not invoiced as time and material while the subscription runs. Every job of "
             "the customer: also the repairs and other jobs of the customer, not only the planned visits.")

    _fs_job_interval_positive = models.Constraint(
        'CHECK(fs_job_interval > 0)', 'The number of periods between two visits must be greater than zero.')
