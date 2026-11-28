from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.om_field_service.models.project_task import CLOSED_STATES


class ProjectTask(models.Model):
    _name = 'project.task'
    _inherit = ['project.task', 'om.quality.document.mixin']

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        tasks.filtered(lambda t: t.is_field_service and t.job_type_id)._fs_quality_create_checks()
        return tasks

    def write(self, vals):
        res = super().write(vals)
        if vals.get('job_type_id') or vals.get('project_id'):
            self.filtered(lambda t: t.is_field_service and t.job_type_id)._fs_quality_create_checks()
        return res

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _fs_quality_product(self):
        """ Product the checks are about: the equipment serviced (field service stock), if any. """
        self.ensure_one()
        equipment = self.equipment_id if 'equipment_id' in self._fields else False
        return equipment.product_id if equipment else self.env['product.product']

    def _fs_quality_create_checks(self):
        """ The checks of the control points of the job type, once per point and job. """
        Point = self.env['om.quality.point']
        for job in self.sudo():
            if job.job_state in CLOSED_STATES:
                continue
            company = job._fs_company()
            points = Point._get_points('fs_job', company, Domain('fs_job_type_ids', 'in', job.job_type_id.ids))
            existing = job._om_quality_checks().point_id
            product = job._fs_quality_product()
            for point in (points - existing)._filter_product(product, job.partner_id):
                if point._should_check(product):
                    job._om_quality_create_checks(point, product, job.partner_id)

    def _fs_quality_open_checks(self):
        """ The checks that keep the job from being done. """
        self.ensure_one()
        checks = self._om_quality_checks()
        blocking = checks.filtered('blocking_pending')
        if self._fs_company().fs_quality_required:
            blocking |= checks.filtered(lambda c: c.state == 'todo')
        return blocking

    def _fs_check_done(self):
        super()._fs_check_done()
        for job in self:
            open_checks = job.sudo()._fs_quality_open_checks()
            if open_checks:
                raise UserError(self.env._(
                    "Do the quality checks of %(job)s first: %(checks)s",
                    job=job.display_name,
                    checks=', '.join(check.title or check.name for check in open_checks)))

    def action_fs_quality_checks(self):
        self.ensure_one()
        self._fs_quality_create_checks()
        return self.action_om_quality_dialog()

    # ------------------------------------------------------------------
    # Phone screen
    # ------------------------------------------------------------------

    def _fs_mobile_data(self):
        data = super()._fs_mobile_data()
        checks = self.sudo()._om_quality_checks().sorted(lambda c: (c.state != 'todo', c.id))
        labels = dict(checks._fields['state']._description_selection(self.env))
        data['extra']['quality'] = [{
            'id': check.id,
            'title': check.title or check.point_id.name or check.name,
            'state': check.state,
            'state_label': labels.get(check.state, ''),
            'test_type': check.test_type,
            'blocking': check.blocking_pending,
            'result': check.result_summary or '',
        } for check in checks]
        return data

    def fs_mobile_quality_action(self, check_id=False):
        """ The check screen of quality, for one check of the job or all of them. """
        self.ensure_one()
        checks = self._om_quality_checks()
        if check_id:
            checks = checks.filtered(lambda c: c.id == check_id)
        return checks.sorted(lambda c: (c.state != 'todo', c.id))._action_open_dialog(
            title=self.job_number or self.name)

    @api.model
    def _fs_quality_demo_checks(self):
        """ Demo data: the checks of the open demo jobs. """
        self.search([('is_field_service', '=', True), ('job_type_id', '!=', False),
                     ('job_state', 'not in', CLOSED_STATES)])._fs_quality_create_checks()
