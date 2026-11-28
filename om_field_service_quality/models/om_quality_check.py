from markupsafe import Markup

from odoo import api, fields, models


class OmQualityCheck(models.Model):
    _inherit = 'om.quality.check'

    fs_job_id = fields.Many2one(
        'project.task', compute='_compute_fs_job_id', store=True, index='btree_not_null',
        string='Field Service Job')

    @api.depends('res_model', 'res_id')
    def _compute_fs_job_id(self):
        for check in self:
            check.fs_job_id = check.res_id if check.res_model == 'project.task' else False

    def _prepare_alert_values(self):
        values = super()._prepare_alert_values()
        job = self.fs_job_id.sudo()
        if not job:
            return values
        values['partner_id'] = job.partner_id.commercial_partner_id.id or values.get('partner_id')
        values['name'] = f"{values['name']} - {job.job_number or job.name}"
        # the equipment of the customer worked on (field service stock), when recorded
        equipment = job.equipment_id if 'equipment_id' in job._fields else False
        if equipment and equipment.product_id and not values.get('product_id'):
            values['product_id'] = equipment.product_id.id
        if job.site_equipment or equipment:
            note = self.env._("Job %(job)s, equipment at the site: %(equipment)s",
                              job=job.job_number or job.name,
                              equipment=equipment.display_name if equipment else job.site_equipment)
            values['description'] = Markup('%s<p>%s</p>') % (values.get('description') or '', note)
        return values
