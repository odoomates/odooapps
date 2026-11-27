from odoo import fields, models


class OmFsJobType(models.Model):
    _inherit = 'om.fs.job.type'

    quality_point_ids = fields.Many2many(
        'om.quality.point', 'om_quality_point_fs_job_type_rel', 'job_type_id', 'point_id',
        string='Quality Control Points', domain="[('point_type', '=', 'fs_job')]",
        help="Quality checks the technician does on each job of this type.")
