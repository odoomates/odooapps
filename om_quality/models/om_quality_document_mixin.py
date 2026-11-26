from odoo import fields, models
from odoo.fields import Domain


class OmQualityDocumentMixin(models.AbstractModel):
    """ Quality checks on a document: the counters of its Quality Checks button, the check
    screen, and the checks that hold it. The apps that hook quality into a document (transfers,
    manufacturing orders...) inherit this and give the domain of its checks. """
    _name = 'om.quality.document.mixin'
    _description = 'Document with Quality Checks'

    om_quality_check_count = fields.Integer(compute='_compute_om_quality_counts', string='Quality Checks')
    om_quality_todo_count = fields.Integer(compute='_compute_om_quality_counts', string='Quality Checks to Do')
    om_quality_failed_count = fields.Integer(compute='_compute_om_quality_counts', string='Failed Quality Checks')
    om_quality_alert_count = fields.Integer(compute='_compute_om_quality_counts', string='Non-conformances Count')
    om_quality_state = fields.Selection([
        ('none', 'No Check'),
        ('todo', 'To Do'),
        ('failed', 'Failed'),
        ('passed', 'Passed'),
    ], compute='_compute_om_quality_counts', string='Quality')

    def _om_quality_check_domain(self):
        """ The checks of the documents of `self`. """
        return Domain('res_model', '=', self._name) & Domain('res_id', 'in', self.ids)

    def _om_quality_document_of_check(self, check):
        """ The document of `self` a check belongs to. """
        return self.browse(check.res_id) if check.res_model == self._name else self.browse()

    def _om_quality_checks(self):
        if not self.ids:
            return self.env['om.quality.check']
        return self.env['om.quality.check'].search(self._om_quality_check_domain() & Domain('state', '!=', 'cancel'))

    def _compute_om_quality_counts(self):
        checks = self._om_quality_checks()
        per_document = {document.id: self.env['om.quality.check'] for document in self}
        for check in checks:
            for document in self._om_quality_document_of_check(check):
                if document.id in per_document:
                    per_document[document.id] |= check
        for document in self:
            document_checks = per_document.get(document.id, self.env['om.quality.check'])
            document.om_quality_check_count = len(document_checks)
            document.om_quality_todo_count = len(document_checks.filtered(lambda c: c.state == 'todo'))
            document.om_quality_failed_count = len(document_checks.filtered(lambda c: c.state == 'failed'))
            document.om_quality_alert_count = len(document_checks.alert_ids)
            if not document_checks:
                document.om_quality_state = 'none'
            elif document.om_quality_todo_count:
                document.om_quality_state = 'todo'
            elif document.om_quality_failed_count:
                document.om_quality_state = 'failed'
            else:
                document.om_quality_state = 'passed'

    def _om_quality_blocking_checks(self):
        if not self.ids:
            return self.env['om.quality.check']
        return self.env['om.quality.check'].search(
            self._om_quality_check_domain() & Domain('blocking_pending', '=', True))

    def _om_quality_block_action(self, checks):
        """ The check screen opened instead of validating: the checks that hold the documents. """
        return checks._action_open_dialog(
            title=self.env._('Quality Checks to Pass'),
            message=self.env._(
                "%(documents)s waits for these quality checks. Pass them, decide what to do with a "
                "failed one, or ask a quality manager to override them; then try again.",
                documents=', '.join(self.mapped('display_name'))))

    def action_om_quality_dialog(self):
        checks = self._om_quality_checks().sorted(lambda c: (c.state != 'todo', c.id))
        return checks._action_open_dialog(title=', '.join(self.mapped('display_name')))

    def action_om_quality_checks(self):
        action = self.env['ir.actions.act_window']._for_xml_id('om_quality.action_om_quality_check')
        action['domain'] = list(self._om_quality_check_domain())
        action['context'] = {'search_default_filter_not_cancel': 1}
        action['display_name'] = self.env._('Quality Checks')
        return action

    def action_om_quality_alerts(self):
        alerts = self._om_quality_checks().alert_ids
        action = self.env['ir.actions.act_window']._for_xml_id('om_quality.action_om_quality_alert')
        action['domain'] = [('id', 'in', alerts.ids)]
        action['context'] = {}
        if len(alerts) == 1:
            action.update({'res_id': alerts.id, 'views': [(False, 'form')], 'view_mode': 'form'})
        return action

    def _om_quality_create_checks(self, point, product, partner, values=None):
        """ Create the check of `point` on the document `self`, with extra `values`. """
        check_values = point._prepare_check_values(product=product, partner=partner, document=self)
        check_values.update(values or {})
        return self.env['om.quality.check'].sudo().create(check_values)
