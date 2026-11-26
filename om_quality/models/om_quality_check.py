from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext, is_html_empty

from .om_quality_point import TEST_TYPES

CHECK_STATES = [
    ('todo', 'To Do'),
    ('passed', 'Passed'),
    ('failed', 'Failed'),
    ('cancel', 'Cancelled'),
]


class OmQualityCheck(models.Model):
    _name = 'om.quality.check'
    _description = 'Quality Check'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(string='Reference', required=True, readonly=True, copy=False, default='/', index='trigram')
    point_id = fields.Many2one('om.quality.point', string='Control Point', index=True, check_company=True, tracking=True)
    title = fields.Char(compute='_compute_from_point', store=True, readonly=False, precompute=True)
    team_id = fields.Many2one(
        'om.quality.team', string='Team', index=True, check_company=True,
        compute='_compute_from_point', store=True, readonly=False, precompute=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)
    test_type = fields.Selection(
        TEST_TYPES, string='Test', required=True,
        compute='_compute_from_point', store=True, readonly=False, precompute=True)
    is_blocking = fields.Boolean(
        string='Blocking', compute='_compute_from_point', store=True, readonly=False, precompute=True,
        help="The document waits for this check: it cannot be validated until the check passes.")
    instructions = fields.Html(related='point_id.instructions', string='Instructions')
    instruction_file = fields.Binary(related='point_id.instruction_file', string='Instruction File')
    instruction_filename = fields.Char(related='point_id.instruction_filename', string='Instruction File Name')
    failure_message = fields.Text(related='point_id.failure_message', string='Failure Message')
    template_id = fields.Many2one(related='point_id.template_id', string='Inspection Template')

    state = fields.Selection(CHECK_STATES, string='Status', required=True, default='todo', index=True, tracking=True, copy=False)
    product_id = fields.Many2one('product.product', string='Product', index=True, check_company=True)
    product_categ_id = fields.Many2one(related='product_id.categ_id', string='Product Category', store=True)
    partner_id = fields.Many2one('res.partner', string='Partner', index=True, check_company=True)
    user_id = fields.Many2one('res.users', string='Assigned To', check_company=True, domain="[('share', '=', False)]")
    done_user_id = fields.Many2one('res.users', string='Done By', readonly=True, copy=False)
    date_done = fields.Datetime(string='Done On', readonly=True, copy=False, index=True)
    note = fields.Html(string='Notes')
    reason_id = fields.Many2one('om.quality.reason', string='Failure Reason', tracking=True)
    measure_line_ids = fields.One2many('om.quality.measure.line', 'check_id', string='Measures', copy=False)
    photo_ids = fields.Many2many(
        'ir.attachment', 'om_quality_check_photo_rel', 'check_id', 'attachment_id', string='Photos', copy=False)
    photo_count = fields.Integer(compute='_compute_photo_count', string='Photos Count')
    result_summary = fields.Char(compute='_compute_result_summary', string='Result')

    res_model = fields.Char(string='Document Model', index=True, readonly=True)
    res_id = fields.Many2oneReference(string='Document ID', model_field='res_model', index=True, readonly=True)
    document_name = fields.Char(string='Document', compute='_compute_document_name', store=True)
    document_ref = fields.Reference(selection='_selection_document_model', compute='_compute_document_ref', string='Linked Document')

    disposition = fields.Selection(
        [('retest', 'Retest'), ('accepted', 'Accepted by override')], string='Decision', readonly=True, copy=False, tracking=True,
        help="What was done after the failure.")
    retest_of_id = fields.Many2one('om.quality.check', string='Retest Of', readonly=True, copy=False, index='btree_not_null')
    retest_ids = fields.One2many('om.quality.check', 'retest_of_id', string='Retests')
    is_overridden = fields.Boolean(string='Overridden', readonly=True, copy=False, tracking=True)
    override_reason = fields.Text(readonly=True, copy=False)
    override_user_id = fields.Many2one('res.users', string='Overridden By', readonly=True, copy=False)
    override_date = fields.Datetime(string='Overridden On', readonly=True, copy=False)
    blocking_pending = fields.Boolean(
        string='Waiting', compute='_compute_blocking_pending', store=True, index=True,
        help="A blocking check that is not passed, decided nor overridden: it holds its document.")
    alert_ids = fields.Many2many(
        'om.quality.alert', 'om_quality_alert_check_rel', 'check_id', 'alert_id', string='Non-conformances', copy=False)
    alert_count = fields.Integer(compute='_compute_alert_count', string='Non-conformances Count')

    @api.depends('point_id')
    def _compute_from_point(self):
        for check in self:
            point = check.point_id
            if not point:
                check.test_type = check.test_type or 'passfail'
                continue
            check.title = point.name
            check.team_id = point.team_id
            check.test_type = point.test_type
            check.is_blocking = point.is_blocking

    @api.depends('photo_ids')
    def _compute_photo_count(self):
        for check in self:
            check.photo_count = len(check.photo_ids)

    @api.depends('alert_ids')
    def _compute_alert_count(self):
        for check in self:
            check.alert_count = len(check.alert_ids)

    @api.depends('state', 'is_blocking', 'is_overridden', 'disposition')
    def _compute_blocking_pending(self):
        for check in self:
            check.blocking_pending = check.is_blocking and not check.is_overridden and (
                check.state == 'todo' or (check.state == 'failed' and not check.disposition))

    @api.depends('res_model', 'res_id')
    def _compute_document_name(self):
        for check in self:
            document = check._get_document()
            check.document_name = document.sudo().display_name if document else False

    @api.model
    def _selection_document_model(self):
        return [(model.model, model.name) for model in self.env['ir.model'].sudo().search([])]

    @api.depends('res_model', 'res_id')
    def _compute_document_ref(self):
        for check in self:
            document = check._get_document()
            check.document_ref = f'{document._name},{document.id}' if document else False

    @api.depends('state', 'test_type', 'measure_line_ids.value', 'measure_line_ids.result')
    def _compute_result_summary(self):
        for check in self:
            lines = check.measure_line_ids.filtered('value_set')
            if check.test_type == 'measure' and lines:
                values = ', '.join(line._format_value() for line in lines)
                check.result_summary = values
            elif check.test_type == 'template' and check.measure_line_ids:
                ok = len(check.measure_line_ids.filtered('is_ok'))
                check.result_summary = self.env._('%(ok)s of %(total)s in limits', ok=ok, total=len(check.measure_line_ids))
            else:
                check.result_summary = False

    def _get_document(self):
        self.ensure_one()
        if self.res_model and self.res_id and self.res_model in self.env:
            document = self.env[self.res_model].browse(self.res_id).exists()
            return document
        return None

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == '/':
                company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('om.quality.check') or '/'
        checks = super().create(vals_list)
        checks.filtered(lambda c: not c.measure_line_ids)._create_measure_lines()
        return checks

    def _create_measure_lines(self):
        """ One line per sample of the measure of the point, or per sample of each parameter
        of its inspection template. """
        values = []
        for check in self:
            point = check.point_id
            if check.test_type == 'measure' and point:
                for sample in range(1, max(point.samples, 1) + 1):
                    values.append({
                        'check_id': check.id,
                        'name': point.name,
                        'sequence': sample,
                        'sample': sample,
                        'test_kind': 'measure',
                        'norm_min': point.norm_min,
                        'norm_target': point.norm_target,
                        'norm_max': point.norm_max,
                        'uom_id': point.uom_id.id,
                    })
            elif check.test_type == 'template' and point.template_id:
                sequence = 0
                for parameter in point.template_id.parameter_ids:
                    for sample in range(1, max(parameter.samples, 1) + 1):
                        sequence += 1
                        values.append({
                            'check_id': check.id,
                            'parameter_id': parameter.id,
                            'name': parameter.name,
                            'sequence': sequence,
                            'sample': sample,
                            'test_kind': parameter.test_kind,
                            'norm_min': parameter.norm_min,
                            'norm_target': parameter.norm_target,
                            'norm_max': parameter.norm_max,
                            'uom_id': parameter.uom_id.id,
                            'instructions': parameter.instructions,
                        })
        if values:
            self.env['om.quality.measure.line'].create(values)

    def unlink(self):
        if any(check.state in ('passed', 'failed') for check in self) and not self.env.is_superuser():
            if not self.env.user.has_group('om_quality.group_om_quality_manager'):
                raise UserError(self.env._("Only a quality manager can delete a recorded check."))
        return super().unlink()

    # ------------------------------------------------------------
    # Results
    # ------------------------------------------------------------

    def _check_editable(self):
        for check in self:
            if check.state == 'cancel':
                raise UserError(self.env._("The check %s is cancelled.", check.name))

    def action_pass(self):
        self._check_editable()
        for check in self:
            if check.test_type == 'picture' and not check.photo_ids:
                raise UserError(self.env._("Add a photo to the check %s before passing it.", check.name))
            if check.test_type in ('measure', 'template'):
                check._evaluate_lines(raise_missing=True)
        self._set_result('passed')
        return True

    def action_fail(self):
        self._check_editable()
        self._set_result('failed')
        return True

    def action_record_measures(self):
        """ Measures and templates: the result follows the recorded values and their limits. """
        self._check_editable()
        for check in self:
            if check.test_type not in ('measure', 'template'):
                continue
            ok = check._evaluate_lines(raise_missing=True)
            check._set_result('passed' if ok else 'failed')
        return True

    def _evaluate_lines(self, raise_missing=False):
        self.ensure_one()
        missing = self.measure_line_ids.filtered(lambda line: not line._has_value())
        if missing and raise_missing:
            raise UserError(self.env._(
                "Record every value of the check %(check)s first: %(lines)s.",
                check=self.name, lines=', '.join(missing.mapped('display_name'))))
        return all(line.is_ok for line in self.measure_line_ids)

    def _set_result(self, state):
        now = fields.Datetime.now()
        for check in self:
            previous = check.state
            check.write({
                'state': state,
                'done_user_id': self.env.user.id,
                'date_done': now,
            })
            if state == 'failed' and previous != 'failed':
                check._on_failure()
            elif state == 'passed' and previous != 'passed':
                check._on_pass()

    def _on_failure(self):
        """ Hook: a check just failed. Raises the non-conformance when the point asks for it. """
        self.ensure_one()
        if self.alert_ids:
            return
        original = self.retest_of_id
        while original.retest_of_id and not original.alert_ids:
            original = original.retest_of_id
        if original.alert_ids:
            original.alert_ids.sudo().check_ids = [(4, self.id)]
            for alert in original.alert_ids:
                alert.sudo().message_post(body=self.env._("The retest %s failed too.", self._get_html_link()))
        elif self.point_id.create_alert:
            self._create_alert()

    def _on_pass(self):
        """ Hook: a check just passed. """
        self.ensure_one()

    def action_reset(self):
        for check in self:
            if check.state == 'cancel' or check.is_overridden or check.disposition:
                continue
            check.write({'state': 'todo', 'done_user_id': False, 'date_done': False, 'disposition': False})
        return True

    def action_cancel(self):
        self.write({'state': 'cancel'})
        return True

    def action_retest(self):
        """ A failed check gets a new check for the same goods: the new one holds the document now. """
        self.ensure_one()
        if self.state != 'failed':
            raise UserError(self.env._("Only a failed check can be tested again."))
        retest = self.copy(self._prepare_retest_values())
        self.disposition = 'retest'
        self.message_post(body=self.env._("Retest %s created.", retest._get_html_link()))
        return retest._action_open_dialog()

    def _prepare_retest_values(self):
        self.ensure_one()
        return {
            'retest_of_id': self.id,
            'res_model': self.res_model,
            'res_id': self.res_id,
            'title': self.title,
            'note': False,
            'reason_id': False,
        }

    # ------------------------------------------------------------
    # Override
    # ------------------------------------------------------------

    def _check_override_rights(self):
        if not self.env.user.has_group('om_quality.group_om_quality_manager'):
            raise AccessError(self.env._("Only a quality manager can override a blocking check."))

    def action_override(self):
        self._check_override_rights()
        return {
            'name': self.env._('Override Blocking Check'),
            'type': 'ir.actions.act_window',
            'res_model': 'om.quality.override',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_check_ids': self.ids},
        }

    def _do_override(self, reason):
        self._check_override_rights()
        now = fields.Datetime.now()
        for check in self:
            values = {
                'is_overridden': True,
                'override_reason': reason,
                'override_user_id': self.env.user.id,
                'override_date': now,
            }
            if check.state == 'failed':
                values['disposition'] = 'accepted'
            check.write(values)
            body = Markup('%s<br/>%s') % (
                self.env._("Blocking check overridden by %s.", self.env.user.name), reason)
            check.message_post(body=body)
            document = check._get_document()
            if document and hasattr(document, 'message_post'):
                document.message_post(body=Markup('%s<br/>%s') % (
                    self.env._("Blocking check %(check)s overridden by %(user)s.",
                               check=check._get_html_link(), user=self.env.user.name), reason))

    # ------------------------------------------------------------
    # Non-conformance
    # ------------------------------------------------------------

    def _prepare_alert_values(self):
        self.ensure_one()
        document = self._get_document()
        title = self.title or self.point_id.name or self.name
        return {
            'name': self.env._('Failed: %(check)s', check=title) + (f' - {self.product_id.display_name}' if self.product_id else ''),
            'team_id': self.team_id.id,
            'company_id': self.company_id.id,
            'product_id': self.product_id.id,
            'partner_id': self.partner_id.id,
            'reason_id': self.reason_id.id,
            'check_ids': [(4, self.id)],
            'res_model': document._name if document else False,
            'res_id': document.id if document else False,
            'description': self.note if not is_html_empty(self.note) else False,
        }

    def _create_alert(self):
        self.ensure_one()
        alert = self.env['om.quality.alert'].sudo().create(self._prepare_alert_values())
        self.message_post(body=self.env._("Non-conformance %s raised.", alert._get_html_link()))
        return alert

    def action_create_alert(self):
        self.ensure_one()
        alert = self.alert_ids[:1] or self._create_alert()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'om.quality.alert',
            'res_id': alert.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def action_view_alerts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_quality.action_om_quality_alert')
        action['domain'] = [('id', 'in', self.alert_ids.ids)]
        action['context'] = {}
        if len(self.alert_ids) == 1:
            action.update({'res_id': self.alert_ids.id, 'views': [(False, 'form')], 'view_mode': 'form'})
        return action

    def action_open_document(self):
        self.ensure_one()
        document = self._get_document()
        if not document:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': document._name,
            'res_id': document.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    # ------------------------------------------------------------
    # Check screen
    # ------------------------------------------------------------

    def _action_open_dialog(self, title=None, message=None):
        return {
            'type': 'ir.actions.client',
            'tag': 'om_quality_check_dialog',
            'name': title or self.env._('Quality Checks'),
            'target': 'new',
            'params': {'check_ids': self.ids, 'message': message or ''},
            'context': {'footer': False, 'dialog_size': 'extra-large'},
        }

    def action_open_dialog(self):
        return self._action_open_dialog(title=self[:1].document_name if len(self) == 1 else None)

    def _dialog_actions(self):
        """ The buttons offered after the result: (method, label, style). """
        self.ensure_one()
        actions = []
        if self.state == 'failed' and not self.disposition and not self.is_overridden:
            actions.append(('action_retest', self.env._('Retest'), 'secondary'))
        if self.state == 'failed':
            label = self.env._('Open Non-conformance') if self.alert_ids else self.env._('Raise Non-conformance')
            actions.append(('action_create_alert', label, 'secondary'))
        return actions

    def _dialog_values(self):
        self.ensure_one()
        disposition = dict(self._fields['disposition']._description_selection(self.env)).get(self.disposition)
        return {
            'id': self.id,
            'name': self.name,
            'title': self.title or self.point_id.name or self.name,
            'test_type': self.test_type,
            'state': self.state,
            'is_blocking': self.is_blocking,
            'blocking_pending': self.blocking_pending,
            'product': self.product_id.display_name or '',
            'partner': self.partner_id.display_name or '',
            'document': self.document_name or '',
            'extra': [],
            'instructions': self.instructions if not is_html_empty(self.instructions) else '',
            'instruction_file_url': (
                f'/web/content/om.quality.point/{self.point_id.id}/instruction_file?download=true'
                if self.point_id.instruction_file else ''),
            'instruction_filename': self.point_id.instruction_filename or '',
            'failure_message': self.failure_message or '',
            'note': html2plaintext(self.note) if not is_html_empty(self.note) else '',
            'reason_id': self.reason_id.id or False,
            'done_by': self.done_user_id.name or '',
            'date_done': fields.Datetime.to_string(self.date_done) if self.date_done else '',
            'is_overridden': self.is_overridden,
            'override_reason': self.override_reason or '',
            'disposition': disposition or '',
            'alert': self.alert_ids[:1].display_name or '',
            'lines': [line._dialog_values() for line in self.measure_line_ids],
            'photos': [{'id': photo.id, 'name': photo.name, 'url': f'/web/image/{photo.id}'} for photo in self.photo_ids],
            'actions': [{'method': method, 'label': label, 'style': style} for method, label, style in self._dialog_actions()],
        }

    @api.model
    def om_quality_dialog_data(self, check_ids):
        checks = self.browse(check_ids).exists()
        checks.check_access('read')
        return {
            'checks': [check._dialog_values() for check in checks],
            'reasons': [[reason.id, reason.display_name] for reason in self.env['om.quality.reason'].search([])],
            'can_override': self.env.user.has_group('om_quality.group_om_quality_manager'),
        }

    def om_quality_dialog_save(self, values):
        """ The check screen saves the note, the failure reason and the values of the lines. """
        self.ensure_one()
        self._check_editable()
        write = {}
        if 'note' in values:
            note = (values['note'] or '').strip()
            write['note'] = Markup('<p>%s</p>') % note if note else False
        if 'reason_id' in values:
            write['reason_id'] = values['reason_id'] or False
        if write:
            self.write(write)
        for line_values in values.get('lines', []):
            line = self.measure_line_ids.filtered(lambda line: line.id == line_values.get('id'))
            if not line:
                continue
            line_write = {}
            if 'value' in line_values:
                value = line_values['value']
                line_write.update({'value': float(value) if value not in (None, '') else 0.0,
                                   'value_set': value not in (None, '')})
            if 'result' in line_values:
                line_write['result'] = line_values['result'] or False
            line.write(line_write)
        return True

    def om_quality_dialog_add_photo(self, name, data):
        self.ensure_one()
        self._check_editable()
        attachment = self.env['ir.attachment'].create({
            'name': name or self.env._('Photo'),
            'datas': data,
            'res_model': self._name,
            'res_id': self.id,
        })
        self.photo_ids = [(4, attachment.id)]
        return {'id': attachment.id, 'name': attachment.name, 'url': f'/web/image/{attachment.id}'}

    def om_quality_dialog_remove_photo(self, attachment_id):
        self.ensure_one()
        self._check_editable()
        attachment = self.photo_ids.filtered(lambda photo: photo.id == attachment_id)
        self.photo_ids = [(3, attachment_id)]
        attachment.unlink()
        return True

    def om_quality_dialog_override(self, reason):
        self.ensure_one()
        self._do_override(reason)
        return True

    def om_quality_dialog_action(self, method):
        """ Run a button of the check screen: only the ones the screen offers. """
        self.ensure_one()
        allowed = {name for name, _label, _style in self._dialog_actions()} | {
            'action_pass', 'action_fail', 'action_record_measures', 'action_reset', 'action_override'}
        if method not in allowed:
            raise UserError(self.env._("This action is not available on the check."))
        result = getattr(self, method)()
        return result if isinstance(result, dict) else False
