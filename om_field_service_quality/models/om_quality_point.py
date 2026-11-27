from odoo import api, fields, models
from odoo.exceptions import ValidationError


class OmQualityPoint(models.Model):
    _inherit = 'om.quality.point'

    point_type = fields.Selection(
        selection_add=[('fs_job', 'Field Service Jobs')], ondelete={'fs_job': 'set default'})
    fs_job_type_ids = fields.Many2many(
        'om.fs.job.type', 'om_quality_point_fs_job_type_rel', 'point_id', 'job_type_id', string='Job Types',
        help="The field service jobs of these types get the check, done by the technician on site.")

    @api.constrains('point_type', 'fs_job_type_ids')
    def _check_fs_job_types(self):
        for point in self:
            if point.point_type == 'fs_job' and not point.fs_job_type_ids:
                raise ValidationError(self.env._("Choose the job types of the control point %s.", point.name))
