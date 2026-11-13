import re

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.om_whatsapp.tools import MetaApiError

# {{ object.partner_id.name }} in the body of Odoo; {{1}} in the one of Meta
EXPRESSION = re.compile(r'\{\{\s*(.+?)\s*\}\}')
META_VARIABLE = re.compile(r'\{\{\s*(\d+)\s*\}\}')
META_STATES = [
    ('draft', 'Not Submitted'),
    ('PENDING', 'In Review'),
    ('APPROVED', 'Approved'),
    ('REJECTED', 'Rejected'),
    ('PAUSED', 'Paused'),
    ('DISABLED', 'Disabled'),
]
# changing these makes an approved template one to submit again
META_FIELDS = {'body', 'report_id', 'meta_name', 'meta_category', 'meta_language', 'meta_footer'}


class OmWhatsappTemplate(models.Model):
    """ The templates of a Meta account are approved by Meta before they go
    out: they are the one way to write to a number that has not written in
    the last 24 hours. The body keeps its {{ object... }} fields; Meta gets
    them as {{1}}, {{2}}... with sample values, and the report as a PDF
    header. """
    _inherit = 'om.whatsapp.template'

    meta_name = fields.Char('Name in Meta', compute='_compute_meta_name', store=True, readonly=False, copy=False,
                            help="Lowercase letters, digits and underscores; unique with the language.")
    meta_category = fields.Selection([
        ('UTILITY', 'Utility'),
        ('MARKETING', 'Marketing'),
        ('AUTHENTICATION', 'Authentication'),
    ], string='Category', default='UTILITY',
        help="Utility: about an order, an invoice, an appointment of the customer. Marketing: offers, news. Meta may "
             "change the category it finds wrong.")
    meta_language = fields.Char('Language Code', default='en_US',
                                help="The language of the text, as Meta names it: en_US, en, fr, es, ar, ml...")
    meta_footer = fields.Char('Footer', help="A short grey line under the text, without fields.")
    meta_status = fields.Selection(META_STATES, string='Meta Status', default='draft', readonly=True, copy=False)
    meta_reason = fields.Char('Reason of Meta', readonly=True, copy=False)
    meta_template_id = fields.Char('Meta Template ID', readonly=True, copy=False, index='btree_not_null')
    meta_waba_id = fields.Char('Business Account ID', readonly=True, copy=False)
    meta_body = fields.Text('Text for Meta', compute='_compute_meta_body')
    variable_ids = fields.One2many('om.whatsapp.template.variable', 'template_id', string='Variables', copy=True)
    is_meta = fields.Boolean(compute='_compute_is_meta')

    @api.depends('name')
    def _compute_meta_name(self):
        for template in self.filtered(lambda t: not t.meta_name):
            template.meta_name = re.sub(r'[^a-z0-9]+', '_', (template.name or '').lower()).strip('_')[:512] or False

    @api.depends('account_id.provider')
    def _compute_is_meta(self):
        for template in self:
            template.is_meta = template.account_id.provider == 'meta'

    @api.depends('body')
    def _compute_meta_body(self):
        for template in self:
            template.meta_body = template._meta_text()[0] if template.body else False

    @api.depends('body', 'report_id', 'model', 'account_id.provider', 'meta_footer', 'variable_ids.expression',
                 'variable_ids.sample')
    def _compute_preview(self):
        super()._compute_preview()

    def _om_whatsapp_preview_values(self, expressions):
        """ For Meta, the samples given for its review first. """
        if not self.is_meta:
            return super()._om_whatsapp_preview_values(expressions)
        samples = {variable.expression: variable.sample for variable in self.variable_ids if variable.sample}
        return {**super()._om_whatsapp_preview_values([e for e in expressions if e not in samples]), **samples}

    def _om_whatsapp_preview_footer(self):
        if self.is_meta and self.meta_footer:
            return Markup('<div class="o_om_whatsapp_preview_footer">%s</div>') % self.meta_footer
        return super()._om_whatsapp_preview_footer()

    def write(self, vals):
        """ A change of what Meta sees makes an approved template one to
        submit again; a change of the fields of Odoo behind {{1}}, {{2}}...
        does not. """
        if not (META_FIELDS & set(vals)) or self.env.context.get('om_whatsapp_meta_sync'):
            return super().write(vals)
        before = {template: template._meta_signature() for template in self}
        result = super().write(vals)
        changed = self.filtered(lambda t: t.meta_status not in ('draft', 'PENDING') and t._meta_signature() != before[t])
        changed.with_context(om_whatsapp_meta_sync=True).write(
            {'meta_status': 'draft', 'meta_reason': _("Changed: submit it again.")})
        return result

    def _meta_signature(self):
        self.ensure_one()
        return (self._meta_text()[0], bool(self.report_id), self.meta_name, self.meta_category, self.meta_language,
                self.meta_footer)

    # ------------------------------------------------------------
    # THE TEXT OF META
    # ------------------------------------------------------------

    def _meta_text(self):
        """ The body as Meta wants it, and the expressions of its {{1}},
        {{2}}...: one number for each different field. """
        self.ensure_one()
        expressions = []

        def number(match):
            expression = match.group(1)
            if expression not in expressions:
                expressions.append(expression)
            return '{{%d}}' % (expressions.index(expression) + 1)

        return EXPRESSION.sub(number, self.body or ''), expressions

    def _meta_sync_variables(self):
        """ One variable for each field of the body, keeping their samples. """
        self.ensure_one()
        _text, expressions = self._meta_text()
        samples = {variable.expression: variable.sample for variable in self.variable_ids}
        record = self.env[self.model].search([], limit=1) if self.model in self.env else None
        commands = [fields.Command.clear()]
        for index, expression in enumerate(expressions, start=1):
            sample = samples.get(expression)
            if not sample and record:
                sample = self._meta_render_expression(expression, record)
            commands.append(fields.Command.create({
                'sequence': index, 'expression': expression, 'sample': sample or _("Sample %(index)s", index=index),
            }))
        self.variable_ids = commands

    def _meta_render_expression(self, expression, record):
        rendered = self._render_template('{{ %s }}' % expression, record._name, record.ids, engine='inline_template')
        return (rendered.get(record.id) or '').strip()

    def _meta_parameters(self, record):
        """ The values of {{1}}, {{2}}... for ``record``, from the fields of
        the body. Meta refuses empty ones: a dash stands for an empty field. """
        self.ensure_one()
        return [self._meta_render_expression(expression, record) or '-' for expression in self._meta_text()[1]]

    def _meta_check(self):
        self.ensure_one()
        text, expressions = self._meta_text()
        if not self.meta_name or not re.fullmatch(r'[a-z0-9_]+', self.meta_name):
            raise UserError(_("The name in Meta has lowercase letters, digits and underscores only."))
        stripped = text.strip()
        if re.match(r'\{\{\d+\}\}', stripped) or re.search(r'\{\{\d+\}\}$', stripped):
            raise UserError(_("Meta refuses a text that starts or ends with a field: add a word before or after it."))
        if len(text) > 1024:
            raise UserError(_("Meta takes 1024 characters at most in the text of a template."))
        if self.meta_footer and EXPRESSION.search(self.meta_footer):
            raise UserError(_("The footer cannot have fields."))
        return text, expressions

    # ------------------------------------------------------------
    # SUBMIT AND SYNC
    # ------------------------------------------------------------

    def _meta_account(self):
        self.ensure_one()
        if self.account_id.provider != 'meta' or not self.account_id.meta_waba_id:
            raise UserError(_("Set a Meta account, connected, on the template: its templates are approved in its "
                              "WhatsApp business account."))
        return self.account_id

    def action_meta_submit(self):
        """ Submit the template to Meta for approval, or its changes. """
        self.check_access('write')
        for template in self:
            account = template._meta_account()
            text, _expressions = template._meta_check()
            template._meta_sync_variables()
            api = account._meta_api()
            components = []
            if template.report_id:
                components.append({
                    'type': 'HEADER', 'format': 'DOCUMENT',
                    'example': {'header_handle': [template._meta_sample_handle(api)]},
                })
            body = {'type': 'BODY', 'text': text}
            if template.variable_ids:
                body['example'] = {'body_text': [template.variable_ids.sorted('sequence').mapped('sample')]}
            components.append(body)
            if template.meta_footer:
                components.append({'type': 'FOOTER', 'text': template.meta_footer})
            payload = {'name': template.meta_name, 'language': template.meta_language, 'category': template.meta_category,
                       'components': components}
            try:
                if template.meta_template_id and template.meta_waba_id == account.meta_waba_id:
                    answer = api.edit_template(template.meta_template_id, {'category': template.meta_category,
                                                                           'components': components})
                else:
                    answer = api.create_template(account.meta_waba_id, payload)
            except MetaApiError as error:
                raise UserError(_("Meta refused %(template)s: %(error)s", template=template.name, error=error)) from error
            template.with_context(om_whatsapp_meta_sync=True).write({
                'meta_template_id': answer.get('id') or template.meta_template_id,
                'meta_waba_id': account.meta_waba_id,
                'meta_status': answer.get('status') if answer.get('status') in dict(META_STATES) else 'PENDING',
                'meta_category': answer.get('category') or template.meta_category,
                'meta_reason': False,
            })
        return True

    def _meta_sample_handle(self, api):
        """ A PDF of the report for a record, uploaded for the review. """
        self.ensure_one()
        record = self.env[self.model].search([], limit=1)
        report = self._om_whatsapp_render_report(record.id) if record else None
        name, content = report or ('sample.pdf', b'%PDF-1.4\n%%EOF\n')
        return api.upload_sample(name, content, 'application/pdf')

    def action_meta_sync(self):
        """ The status of the templates in Meta, now. """
        self.check_access('write')
        for account in self.account_id.filtered(lambda a: a.provider == 'meta' and a.meta_waba_id):
            account._meta_sync_templates()
        return True

    def _meta_ready(self, account):
        """ Whether Meta sends this template from ``account``. """
        self.ensure_one()
        return self.meta_status == 'APPROVED' and bool(self.meta_template_id) and self.meta_waba_id == account.meta_waba_id


class OmWhatsappTemplateVariable(models.Model):
    _name = 'om.whatsapp.template.variable'
    _description = 'WhatsApp Template Variable'
    _order = 'sequence, id'

    template_id = fields.Many2one('om.whatsapp.template', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer('Number', help="It is {{1}}, {{2}}... in the text of Meta.")
    expression = fields.Char('Field', required=True, help="What the body has between {{ }}, e.g. object.partner_id.name.")
    sample = fields.Char('Sample', help="An example value, for the review of Meta.")
