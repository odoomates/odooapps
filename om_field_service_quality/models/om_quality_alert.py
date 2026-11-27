from odoo import api, fields, models


class OmQualityAlert(models.Model):
    _inherit = 'om.quality.alert'

    fs_job_id = fields.Many2one(
        'project.task', compute='_compute_fs_job_id', store=True, index='btree_not_null',
        string='Field Service Job')

    @api.depends('res_model', 'res_id')
    def _compute_fs_job_id(self):
        for alert in self:
            alert.fs_job_id = alert.res_id if alert.res_model == 'project.task' else False

    def action_fs_view_job(self):
        self.ensure_one()
        return self.fs_job_id.action_fs_open_job()
