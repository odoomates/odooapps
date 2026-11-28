import re

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools.safe_eval import safe_eval

from .om_ai_field_engine import FILLABLE_TYPES

NEW_FIELD_TYPES = [
    ('char', 'Text (one line)'),
    ('text', 'Long Text'),
    ('html', 'Formatted Text'),
    ('selection', 'Selection'),
    ('many2one', 'Link to a Record'),
    ('boolean', 'Checkbox'),
    ('float', 'Number'),
]
SYNC_MAX_RECORDS = 10


class OmAiField(models.Model):
    """A field of a model that the AI fills from a prompt with record values."""
    _name = 'om.ai.field'
    _description = 'AI Field'
    _order = 'model_id, sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company')
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade',
                               domain=[('transient', '=', False)])
    model_name = fields.Char(related='model_id.model', string='Model Name')
    field_id = fields.Many2one(
        'ir.model.fields', string='Field', ondelete='cascade',
        domain="[('model_id', '=', model_id), ('ttype', 'in', %s), ('readonly', '=', False), "
               "('store', '=', True)]" % (list(FILLABLE_TYPES),),
        help='The field the AI fills. Pick an existing field, or create a new one below.')
    field_type = fields.Selection(related='field_id.ttype', string='Field Type')
    # creating a new field
    new_field_label = fields.Char(string='New Field Label')
    new_field_name = fields.Char(string='New Field Name', help='Technical name, starting with x_.')
    new_field_type = fields.Selection(NEW_FIELD_TYPES, string='New Field Type', default='char')
    new_field_selection = fields.Text(
        string='Selection Values', help='One value per line, as key:Label (e.g. hot:Hot).')
    new_field_relation_id = fields.Many2one('ir.model', string='Linked Model', ondelete='cascade',
                                            domain=[('transient', '=', False)])
    view_id = fields.Many2one('ir.ui.view', string='Form View Extension', readonly=True, copy=False,
                              ondelete='set null')
    # the prompt
    prompt = fields.Text(
        required=True, translate=True,
        help='What the AI is asked, with record values as {{ field }} or {{ field.sub_field }}, '
             'e.g. Describe the company {{ name }} from {{ city }}, {{ country_id.name }}.')
    instructions = fields.Text(translate=True, help='Extra rules for the AI: tone, length, language...')
    placeholders = fields.Char(compute='_compute_placeholders')
    purpose = fields.Selection([('fast', 'Fast'), ('chat', 'Chat')], default='fast', required=True,
                               help='Which default AI model of the company answers.')
    ai_model_id = fields.Many2one('om.ai.model', string='AI Model', domain=[('cap_chat', '=', True)],
                                  help='Use this model instead of the company default for the purpose.')
    relation_domain = fields.Char(string='Allowed Records', default='[]',
                                  help='For a link to a record: the records the AI may choose from.')
    relation_model = fields.Char(compute='_compute_relation_model')
    domain = fields.Char(string='Apply On', default='[]', help='Only the records matching this filter are filled.')
    overwrite = fields.Boolean(string='Replace Existing Values',
                               help='Fill the field again even when it has a value. Otherwise only empty fields '
                                    'are filled.')
    # when
    trigger_on_change = fields.Boolean(string='When Fields Change',
                                       help='Fill the field in the background when a record is created or one '
                                            'of these fields changes.')
    trigger_field_ids = fields.Many2many('ir.model.fields', 'om_ai_field_trigger_rel', 'ai_field_id', 'field_id',
                                         string='Trigger Fields', domain="[('model_id', '=', model_id)]")
    trigger_cron = fields.Boolean(string='Scheduled for Empty Values',
                                  help='Fill the empty values of existing records by a scheduled action.')
    cron_batch = fields.Integer(string='Records per Run', default=20)
    daily_limit = fields.Integer(string='Records per Day',
                                 help='Stop filling after this many records per day. 0 for no limit.')
    # links and counters
    action_id = fields.Many2one('ir.actions.server', string='Server Action', readonly=True, copy=False,
                                ondelete='set null')
    automation_id = fields.Many2one('base.automation', string='Automation Rule', readonly=True, copy=False,
                                    ondelete='set null')
    fill_count = fields.Integer(string='Records Filled', readonly=True, copy=False)
    today_count = fields.Integer(string='Filled Today', readonly=True, copy=False)
    today_date = fields.Date(readonly=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)
    job_count = fields.Integer(compute='_compute_job_count')

    @api.depends('prompt', 'instructions')
    def _compute_placeholders(self):
        engine = self.env['om.ai.field.engine']
        for ai_field in self:
            ai_field.placeholders = ', '.join(engine._placeholders(
                '%s\n%s' % (ai_field.prompt or '', ai_field.instructions or '')))

    @api.depends('field_id')
    def _compute_relation_model(self):
        for ai_field in self:
            ai_field.relation_model = ai_field.field_id.relation if ai_field.field_id.ttype == 'many2one' else False

    def _compute_job_count(self):
        data = dict(self.env['om.ai.field.job']._read_group(
            [('action_id', 'in', self.action_id.ids), ('state', 'in', ('pending', 'failed'))],
            ['action_id'], ['__count']))
        for ai_field in self:
            ai_field.job_count = data.get(ai_field.action_id, 0)

    @api.onchange('model_id')
    def _onchange_model_id(self):
        if self.field_id and self.field_id.model_id != self.model_id:
            self.field_id = False
        self.trigger_field_ids = False

    @api.onchange('new_field_label')
    def _onchange_new_field_label(self):
        if self.new_field_label and not self.new_field_name:
            name = re.sub(r'[^a-z0-9_]+', '_', self.new_field_label.lower()).strip('_')
            self.new_field_name = 'x_ai_%s' % name if name else False

    @api.constrains('prompt', 'instructions', 'model_id')
    def _check_prompt(self):
        engine = self.env['om.ai.field.engine']
        for ai_field in self:
            try:
                engine._check_template(ai_field.model_name, ai_field.prompt)
            except UserError as error:
                raise ValidationError(error.args[0]) from None

    @api.constrains('field_id', 'model_id')
    def _check_field(self):
        for ai_field in self.filtered('field_id'):
            if ai_field.field_id.model_id != ai_field.model_id:
                raise ValidationError(self.env._('The field must belong to the model.'))
            if ai_field.field_id.ttype not in FILLABLE_TYPES:
                raise ValidationError(self.env._('The AI cannot fill a field of type %s.', ai_field.field_id.ttype))

    # ------------------------------------------------------------------
    # CRUD: server action and automation rule kept in sync
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_links()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('om_ai_field_sync'):
            self._sync_links()
        return res

    def unlink(self):
        actions = self.action_id
        automations = self.automation_id
        views = self.view_id
        res = super().unlink()
        automations.sudo().unlink()
        actions.sudo().unlink()
        views.sudo().unlink()
        return res

    def _sync_links(self):
        Action = self.env['ir.actions.server'].sudo()
        Automation = self.env['base.automation'].sudo()
        for ai_field in self.with_context(om_ai_field_sync=True):
            if not ai_field.field_id:
                continue
            action_vals = {
                'name': self.env._('Fill %s with AI', ai_field.field_id.field_description),
                'model_id': ai_field.model_id.id,
                'state': 'om_ai_fields',
                'om_ai_field_def_id': ai_field.id,
                'om_ai_target_field_ids': [Command.set(ai_field.field_id.ids)],
                'binding_model_id': ai_field.model_id.id if ai_field.active else False,
                'binding_view_types': 'list,form',
            }
            if ai_field.action_id:
                ai_field.action_id.sudo().write(action_vals)
            else:
                ai_field.action_id = Action.create(action_vals)
            wanted = ai_field.active and ai_field.trigger_on_change
            if wanted:
                automation_vals = {
                    'name': self.env._('AI: fill %s', ai_field.field_id.field_description),
                    'model_id': ai_field.model_id.id,
                    'trigger': 'on_create_or_write',
                    'trigger_field_ids': [Command.set(ai_field.trigger_field_ids.ids)],
                    'filter_domain': ai_field.domain if ai_field.domain and ai_field.domain != '[]' else False,
                    'action_server_ids': [Command.set(ai_field.action_id.ids)],
                    'active': True,
                }
                if ai_field.automation_id:
                    ai_field.automation_id.sudo().write(automation_vals)
                else:
                    ai_field.automation_id = Automation.create(automation_vals)
            elif ai_field.automation_id:
                # keep the server action: the automation rule only refers to it
                ai_field.automation_id.sudo().write({'action_server_ids': [Command.clear()]})
                ai_field.automation_id.sudo().unlink()

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def action_create_field(self):
        """Create the new custom field, and show it on the form of the model."""
        self.ensure_one()
        if self.field_id:
            raise UserError(self.env._('This AI field already has a field.'))
        if not self.new_field_label or not self.new_field_name:
            raise UserError(self.env._('Give the label and the technical name of the new field.'))
        name = self.new_field_name.strip()
        if not name.startswith('x_'):
            name = 'x_' + name
        if not re.fullmatch(r'x_[a-z0-9_]+', name):
            raise UserError(self.env._('The technical name may only contain lowercase letters, digits and _.'))
        if name in self.env[self.model_name]._fields:
            raise UserError(self.env._('The model already has a field %s.', name))
        vals = {
            'name': name,
            'field_description': self.new_field_label,
            'model_id': self.model_id.id,
            'ttype': self.new_field_type,
            'state': 'manual',
        }
        if self.new_field_type == 'selection':
            pairs = []
            for line in (self.new_field_selection or '').splitlines():
                if not line.strip():
                    continue
                key, _sep, label = line.partition(':')
                key = key.strip()
                pairs.append((key, (label or key).strip()))
            if not pairs:
                raise UserError(self.env._('Give the selection values, one per line as key:Label.'))
            vals['selection_ids'] = [Command.create({'value': key, 'name': label, 'sequence': index})
                                     for index, (key, label) in enumerate(pairs)]
        elif self.new_field_type == 'many2one':
            if not self.new_field_relation_id:
                raise UserError(self.env._('Choose the model the new field links to.'))
            vals['relation'] = self.new_field_relation_id.model
            vals['on_delete'] = 'set null'
        new_field = self.env['ir.model.fields'].sudo().create(vals)
        self.field_id = new_field
        self._add_to_form_view()
        return True

    def _add_to_form_view(self):
        """Add the field at the end of the main form view of the model."""
        self.ensure_one()
        view = self.env['ir.ui.view'].sudo().search([
            ('model', '=', self.model_name), ('type', '=', 'form'), ('mode', '=', 'primary'),
            ('inherit_id', '=', False),
        ], order='priority, id', limit=1)
        if not view:
            return
        arch = etree.fromstring(view.get_combined_arch())
        widget = ' widget="html"' if self.field_id.ttype == 'html' else ''
        field_xml = '<field name="%s"%s/>' % (self.field_id.name, widget)
        if arch.xpath('//sheet'):
            if arch.xpath("//page[@name='om_ai_fields']/group"):
                path, inner, position = "//page[@name='om_ai_fields']/group", field_xml, 'inside'
            elif arch.xpath('//sheet/notebook'):
                path = '//sheet/notebook'
                inner = ('<page string="%s" name="om_ai_fields"><group>%s</group></page>'
                         % (self.env._('AI'), field_xml))
                position = 'inside'
            else:
                path, inner, position = '//sheet', '<group>%s</group>' % field_xml, 'inside'
        else:
            path, inner, position = '//form', '<group>%s</group>' % field_xml, 'inside'
        self.view_id = self.env['ir.ui.view'].sudo().create({
            'name': 'om_ai_fields.%s.%s' % (self.model_name, self.field_id.name),
            'model': self.model_name,
            'inherit_id': view.id,
            'mode': 'extension',
            'priority': 99,
            'arch': '<data><xpath expr="%s" position="%s">%s</xpath></data>' % (path, position, inner),
        })

    def _get_domain(self):
        self.ensure_one()
        return safe_eval(self.domain or '[]', {'uid': self.env.uid, 'user': self.env.user})

    def _get_relation_domain(self):
        self.ensure_one()
        if self.field_id.ttype != 'many2one':
            return None
        return safe_eval(self.relation_domain or '[]', {'uid': self.env.uid, 'user': self.env.user})

    def action_test(self):
        """Fill the field on one matching record and show the result."""
        self.ensure_one()
        if not self.field_id:
            raise UserError(self.env._('Choose or create the field first.'))
        record = self.env[self.model_name].search(self._get_domain(), limit=1)
        if not record:
            raise UserError(self.env._('No record matches.'))
        result = self._fill_records(record, force=True)
        if result['errors']:
            raise UserError('\n'.join(result['errors']))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.model_name,
            'res_id': record.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_view_jobs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('AI Field Queue'),
            'res_model': 'om.ai.field.job',
            'view_mode': 'list,form',
            'domain': [('action_id', '=', self.action_id.id)],
        }

    # ------------------------------------------------------------------
    # Filling
    # ------------------------------------------------------------------
    def _remaining_today(self):
        self.ensure_one()
        if not self.daily_limit:
            return None
        used = self.today_count if self.today_date == fields.Date.context_today(self) else 0
        return max(0, self.daily_limit - used)

    def _count_filled(self, count):
        self.ensure_one()
        today = fields.Date.context_today(self)
        used = self.today_count if self.today_date == today else 0
        self.sudo().with_context(om_ai_field_sync=True).write({
            'fill_count': self.fill_count + count,
            'today_count': used + count,
            'today_date': today,
        })

    def _fill_records(self, records, force=False):
        """Fill the field on ``records`` now, within the daily limit."""
        self.ensure_one()
        engine = self.env['om.ai.field.engine']
        if not force:
            records = records.filtered_domain(self._get_domain())
        remaining = self._remaining_today()
        if remaining is not None:
            if not remaining:
                return {'filled': 0, 'skipped': len(records), 'errors': [
                    self.env._('%s: the daily limit of records is reached.', self.name)]}
            records = records[:remaining]
        result = engine._fill(records, self.field_id, self.prompt, instructions=self.instructions,
                              purpose=self.purpose, ai_model=self.ai_model_id, overwrite=self.overwrite or force,
                              relation_domain=self._get_relation_domain())
        if result['filled']:
            self._count_filled(result['filled'])
        self.sudo().with_context(om_ai_field_sync=True).last_error = '\n'.join(result['errors'][:10]) or False
        return result

    @api.model
    def _cron_fill_empty(self):
        """Queue the empty values of the AI fields filled on a schedule."""
        Job = self.env['om.ai.field.job']
        for ai_field in self.search([('trigger_cron', '=', True), ('field_id', '!=', False)]):
            remaining = ai_field._remaining_today()
            batch = min(ai_field.cron_batch or 20, remaining if remaining is not None else 10 ** 6)
            if batch <= 0:
                continue
            Model = self.env[ai_field.model_name]
            queued = Job.search([('action_id', '=', ai_field.action_id.id), ('state', '=', 'pending')]).mapped(
                'res_id')
            domain = ai_field._get_domain() + [(ai_field.field_id.name, '=', False), ('id', 'not in', queued)]
            records = Model.search(domain, limit=batch)
            if records:
                Job._enqueue(ai_field.action_id, records)
