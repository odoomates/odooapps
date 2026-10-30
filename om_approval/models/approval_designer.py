from markupsafe import Markup

from odoo import Command, api, models
from odoo.exceptions import UserError
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

# the fields of a flow and of a step the designer edits
FLOW_FIELDS = ('name', 'domain', 'note', 'lock_record', 'lock_after', 'self_approve', 'run_on_approval',
               'amount_field', 'amount_min', 'request_note', 'approve_note', 'refuse_note')
FLOW_RELATIONS = ('button_id', 'fallback_group_id', 'company_id', 'amount_currency_id')
STEP_FIELDS = ('name', 'approver_type', 'field_path', 'domain', 'remind_days', 'escalate_days', 'escalate_type',
               'amount_min', 'approval_mode', 'approval_count')
STEP_RELATIONS = ('group_id', 'escalate_group_id')
NUMBERS = ('remind_days', 'escalate_days', 'amount_min', 'approval_count')
STEP_MANY = ('user_ids', 'escalate_user_ids')

# the buttons, amounts and people of the models a template knows, when their app is installed
PRESETS = {
    'sale.order': {
        'label': _lt('Quotations'), 'amount': 'amount_total', 'limit': 5000, 'high_limit': 20000,
        'confirm': 'action_confirm', 'cancel': 'action_cancel', 'cancel_domain': [('state', '=', 'sale')],
        'responsible': 'user_id', 'leader': 'team_id.user_id', 'group': 'sales_team.group_sale_manager',
        'discount': 'order_line.discount', 'discount_limit': 20,
    },
    'purchase.order': {
        'label': _lt('Purchase Orders'), 'amount': 'amount_total', 'limit': 5000, 'high_limit': 20000,
        'confirm': 'button_confirm', 'cancel': 'button_cancel', 'cancel_domain': [('state', '=', 'purchase')],
        'responsible': 'user_id', 'group': 'purchase.group_purchase_manager',
    },
    'account.move': {
        'label': _lt('Vendor Bills'), 'amount': 'amount_total', 'limit': 5000, 'high_limit': 20000,
        'domain': [('move_type', '=', 'in_invoice')], 'confirm': 'action_post',
        'cancel': 'button_draft', 'cancel_domain': [('state', '=', 'posted')],
        'responsible': 'invoice_user_id', 'group': 'account.group_account_manager',
    },
    'stock.picking': {
        'label': _lt('Transfers'), 'confirm': 'button_validate', 'cancel': 'action_cancel',
        'cancel_domain': [('state', 'not in', ('done', 'cancel'))], 'responsible': 'user_id',
        'group': 'stock.group_stock_manager',
    },
}
# the demo flows of each app, made from the templates once the app is installed, if the database has demo data
DEMO_FLOWS = {
    'sale.order': ('sale', ['two_level', 'discount', 'cancel']),
    'purchase.order': ('purchase', ['amount']),
    'account.move': ('account', ['amount']),
    'stock.picking': ('stock', ['responsible']),
}
# the apps given their demo flows so far: each once, so that the deleted ones stay deleted
DEMO_PARAM = 'om_approval.demo_apps'

# guessed on the other models, the first found
AMOUNT_FIELDS = ('amount_total', 'amount', 'amount_untaxed', 'price_total', 'expected_revenue')
CONFIRM_METHODS = ('action_confirm', 'button_confirm', 'action_post', 'action_validate', 'button_validate',
                   'action_approve', 'action_done')
CANCEL_METHODS = ('action_cancel', 'button_cancel')
RESPONSIBLE_FIELDS = ('user_id', 'invoice_user_id')


class ApprovalRule(models.Model):
    """ The Approval Designer and its gallery: a flow edited as a chain of cards, and flows started from templates. """
    _inherit = 'approval.rule'

    # ------------------------------------------------------------------
    # Designer
    # ------------------------------------------------------------------

    @api.model
    def designer_load(self, flow_id=False, model=False):
        """ :return: a flow as the designer edits it, a new one on `model` when no flow is given, and the choices
                     the designer offers """
        self._designer_check_access()
        flow = self.browse(flow_id).exists() if flow_id else self.browse()
        if flow_id and not flow:
            raise UserError(self.env._('This approval flow no longer exists.'))
        model = flow.model or model
        if not model or model not in self.env:
            raise UserError(self.env._('Choose the kind of record the flow applies to.'))
        data = flow._designer_values() if flow else self._designer_new_values(model)
        return {'flow': data, **self._designer_choices(model), 'preview': self.designer_preview(data)}

    def _designer_values(self):
        self.ensure_one()
        values = {'id': self.id, 'active': self.active, 'model': self.model}
        values.update({name: self[name] for name in FLOW_FIELDS})
        values.update({name: self[name].id or False for name in FLOW_RELATIONS})
        values['domain'] = values['domain'] or '[]'
        values['note'] = values['note'] or ''
        values['amount_field'] = values['amount_field'] or ''
        values['steps'] = [{
            'id': step.id,
            **{name: step[name] or (0 if name in NUMBERS else '') for name in STEP_FIELDS},
            **{name: step[name].id or False for name in STEP_RELATIONS},
            **{name: step[name].ids for name in STEP_MANY},
        } for step in self.step_ids.sorted(lambda s: (s.sequence, s.id))]
        for step in values['steps']:
            step['domain'] = step['domain'] or '[]'
        return values

    @api.model
    def _designer_new_values(self, model):
        defaults = self.default_get(list(FLOW_FIELDS) + list(FLOW_RELATIONS))
        values = {'id': False, 'active': False, 'model': model, 'steps': [], 'button_id': False,
                  'company_id': False, 'fallback_group_id': defaults.get('fallback_group_id') or False,
                  'amount_currency_id': defaults.get('amount_currency_id') or False}
        values.update({name: defaults.get(name) for name in FLOW_FIELDS})
        values.update(name=self.env._('Approval of %s', self.env['ir.model']._get(model).name), domain='[]', note='',
                      amount_field='', amount_min=0)
        return values

    @api.model
    def _designer_choices(self, model):
        """ :return: what the designer offers for `model`: its buttons, its quick conditions, the kinds of
                     approvers and of escalation """
        step_fields = self.env['approval.step']._fields
        buttons = self.env['approval.button']._sync(model)
        return {
            'model_name': self.env['ir.model']._get(model).name,
            'is_document': model in set(self.env['approval.mixin']._inherit_children),
            'buttons': [{'id': button.id, 'name': button.name, 'method': button.method} for button in buttons],
            'quick': self._designer_quick_conditions(model),
            'approver_types': step_fields['approver_type']._description_selection(self.env),
            'escalate_types': step_fields['escalate_type']._description_selection(self.env),
            'user_models': list(self.env['approval.step']._users_models()),
            'step_defaults': {
                **self.env['approval.step'].default_get(list(STEP_FIELDS) + list(STEP_RELATIONS)),
                'id': False, 'name': self.env._('Approval'), 'domain': '[]', 'field_path': '', 'user_ids': [],
                'escalate_user_ids': [], 'group_id': False, 'escalate_group_id': False,
            },
            'multi_company': self.env.user.has_group('base.group_multi_company'),
            'multi_currency': self.env.user.has_group('base.group_multi_currency'),
            'note_modes': self.env['approval.rule']._fields['request_note']._description_selection(self.env),
            'approval_modes': step_fields['approval_mode']._description_selection(self.env),
        }

    @api.model
    def _designer_quick_conditions(self, model):
        """ :return: the conditions offered in one click, e.g. Total above, as label, field path and operator """
        Model = self.env[model]
        preset = PRESETS.get(model, {})
        quick = []
        amount = preset.get('amount') or next(
            (name for name in AMOUNT_FIELDS if Model._fields.get(name) is not None
             and Model._fields[name].type in ('monetary', 'float', 'integer') and Model._fields[name].store), None)
        if amount:
            label = Model._fields[amount]._description_string(self.env)
            quick.append({'label': self.env._('%s above', label), 'path': amount, 'kind': 'amount'})
        if preset.get('discount'):
            quick.append({'label': self.env._('A discount above (%)'), 'path': preset['discount'], 'operator': '>',
                          'kind': 'domain'})
        return quick

    @api.model
    def designer_preview(self, data):
        """ :return: the flow being edited in words, as it would be saved: its summary, its conditions and, per
                     step, who approves it and when """
        empty = {'summary': False, 'conditions': False, 'steps': []}
        if not data.get('model') or data['model'] not in self.env:
            return empty
        vals = self._designer_vals(data)
        vals['step_ids'] = [Command.create(step) for step in self._designer_steps_vals(data)]
        flow = self.new(vals)
        try:
            return {
                'summary': flow._summary(),
                'conditions': flow._describe_conditions() or False,
                'steps': [{'who': step._describe_approvers(), 'when': step._describe_conditions() or False}
                          for step in flow.step_ids],
            }
        except Exception:  # an incomplete flow, e.g. a field path being typed, is described once complete
            return dict(empty, summary=Markup('<p class="text-muted">%s</p>') % self.env._(
                'The summary shows once the flow is complete.'))

    @api.model
    def _designer_vals(self, data):
        vals = {name: data.get(name) for name in FLOW_FIELDS if name in data}
        vals.update({name: data.get(name) or False for name in FLOW_RELATIONS if name in data})
        vals['model_id'] = self.env['ir.model']._get_id(data['model'])
        for name in ('note', 'amount_field'):
            if name in vals and not vals[name]:
                vals[name] = False
        return vals

    @api.model
    def _designer_steps_vals(self, data):
        steps = []
        for index, step in enumerate(data.get('steps') or []):
            vals = {name: step.get(name) for name in STEP_FIELDS if name in step}
            vals.update({name: step.get(name) or False for name in STEP_RELATIONS if name in step})
            vals.update({name: [Command.set(step.get(name) or [])] for name in STEP_MANY if name in step})
            vals['sequence'] = (index + 1) * 10
            if not vals.get('field_path'):
                vals['field_path'] = False
            steps.append(vals)
        return steps

    @api.model
    def designer_save(self, flow_id, data):
        """ Save the flow edited in the designer, its steps in the order of the cards.

        :return: the flow saved, as `designer_load` gives it
        """
        self._designer_check_access()
        vals = self._designer_vals(data)
        steps = self._designer_steps_vals(data)
        flow = self.browse(flow_id).exists() if flow_id else self.browse()
        if flow:
            kept = {step['id'] for step in data.get('steps') or [] if step.get('id')}
            commands = [Command.unlink(step.id) for step in flow.step_ids if step.id not in kept]
            for step, values in zip(data.get('steps') or [], steps, strict=True):
                commands.append(Command.update(step['id'], values) if step.get('id') in flow.step_ids.ids
                                else Command.create(values))
            flow.write({**vals, 'step_ids': commands})
        else:
            flow = self.create({**vals, 'active': bool(data.get('active')),
                                'step_ids': [Command.create(values) for values in steps]})
        return self.designer_load(flow.id)

    @api.model
    def designer_set_active(self, flow_id, active):
        """ Activate or deactivate a flow from the designer. :return: the flow, as `designer_load` gives it """
        self._designer_check_access()
        flow = self.with_context(active_test=False).browse(flow_id).exists()
        if not flow:
            raise UserError(self.env._('This approval flow no longer exists.'))
        flow.active = active
        return self.designer_load(flow.id)

    @api.model
    def _designer_check_access(self):
        if not self.env.user.has_group('om_approval.group_approval_manager'):
            raise UserError(self.env._('Only the approval managers set up the approval flows.'))

    def action_open_designer(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'om_approval_designer',
            'name': self.name,
            'params': {'flow_id': self.id},
        }

    # ------------------------------------------------------------------
    # Gallery
    # ------------------------------------------------------------------

    @api.model
    def _gallery_templates(self):
        """ :return: the templates of the gallery, each a dict of key, name, description, icon, and the needs a model
                     must meet: the keys of its preset (or guess), or 'document' for its own approval """
        return [
            {'key': 'amount', 'icon': 'thumb_up', 'needs': ('confirm', 'amount'),
             'name': self.env._('Approval above an amount'),
             'description': self.env._('Confirming a record above an amount, e.g. a quotation, waits for a '
                                       'manager.')},
            {'key': 'two_level', 'icon': 'account_tree', 'needs': ('confirm', 'amount'),
             'name': self.env._('Two-level approval'),
             'description': self.env._('A manager approves; above a higher amount, you approve too.')},
            {'key': 'responsible', 'icon': 'person_add', 'needs': ('confirm', 'responsible'),
             'name': self.env._('Approval by the person responsible'),
             'description': self.env._('The team leader, or the person responsible for the record, approves it '
                                       'before it is confirmed.')},
            {'key': 'discount', 'icon': 'star', 'needs': ('confirm', 'discount'),
             'name': self.env._('Approval of a discount'),
             'description': self.env._('A quotation with a discount above a percentage waits for a manager.')},
            {'key': 'cancel', 'icon': 'event_busy', 'needs': ('cancel',),
             'name': self.env._('Approval to cancel'),
             'description': self.env._('Cancelling a confirmed record waits for a manager.')},
        ]

    @api.model
    def _gallery_preset(self, model):
        """ :return: the preset of `model`, or what is guessed of it: its buttons, amount and people """
        Model = self.env[model]
        if model in PRESETS:
            preset = dict(PRESETS[model])
            label = preset['label']
            preset['label'] = label._translate(self.env.lang) if hasattr(label, '_translate') else label
        else:
            methods = set(self.env['approval.button']._sync(model).mapped('method'))
            preset = {'label': self.env['ir.model']._get(model).name}
            preset['confirm'] = next((m for m in CONFIRM_METHODS if m in methods), None)
            preset['cancel'] = next((m for m in CANCEL_METHODS if m in methods), None)
            preset['amount'] = next(
                (name for name in AMOUNT_FIELDS if Model._fields.get(name) is not None
                 and Model._fields[name].type in ('monetary', 'float', 'integer') and Model._fields[name].store),
                None)
            preset['responsible'] = next(
                (name for name in RESPONSIBLE_FIELDS if Model._fields.get(name) is not None
                 and Model._fields[name].comodel_name == 'res.users'), None)
            preset.update(limit=5000, high_limit=20000)
        preset['document'] = model in set(self.env['approval.mixin']._inherit_children)
        return {key: value for key, value in preset.items() if value}

    @api.model
    def gallery_load(self, model=False, prefix=False):
        """ :return: the templates and, for each, the models it is ready for, for the gallery; only the models
                     starting with `prefix` when given, e.g. hr. for the HR menu """
        self._designer_check_access()
        installed = [m for m in PRESETS if m in self.env]
        documents = sorted(set(self.env['approval.mixin']._inherit_children) & set(self.env))
        candidates = list(dict.fromkeys(([model] if model and model in self.env else []) + installed + documents))
        if prefix:
            candidates = [name for name in candidates if name.startswith(prefix)]
        presets = {name: self._gallery_preset(name) for name in candidates}
        names = {name: presets[name]['label'] for name in candidates}
        templates = []
        for template in self._gallery_templates():
            ready = [name for name in candidates if all(presets[name].get(need) for need in template['needs'])]
            if prefix and not ready:
                continue
            templates.append({
                'key': template['key'], 'name': template['name'], 'description': template['description'],
                'icon': template['icon'],
                'models': [{'model': name, 'name': names[name], 'preset': name in PRESETS} for name in ready],
            })
        return {'templates': templates, 'model': model or False}

    @api.model
    def gallery_create(self, template_key, model):
        """ Create a flow from a template for `model`, inactive until it is checked.

        :return: the id of the flow
        """
        self._designer_check_access()
        if model not in self.env:
            raise UserError(self.env._('Choose the kind of record the flow applies to.'))
        return self._gallery_flow_create(template_key, model).id

    @api.model
    def _gallery_flow_create(self, template_key, model):
        """ :return: the flow of the template for `model`, inactive """
        template = next((t for t in self._gallery_templates() if t['key'] == template_key), None)
        if template is None:
            raise UserError(self.env._('This template no longer exists.'))
        preset = self._gallery_preset(model)
        missing = [need for need in template['needs'] if not preset.get(need)]
        if missing:
            raise UserError(self.env._('%(template)s does not fit %(model)s: it has no %(missing)s.',
                                       template=template['name'], model=preset['label'], missing=', '.join(missing)))
        values = self._gallery_flow_values(template_key, model, preset)
        if 'button_id' in values and not values['button_id']:
            raise UserError(self.env._('%(template)s does not fit %(model)s: its button is not on its views.',
                                       template=template['name'], model=preset['label']))
        values.update(active=False, model_id=self.env['ir.model']._get_id(model))
        return self.create(values)

    # ------------------------------------------------------------------
    # Demo data
    # ------------------------------------------------------------------

    def _register_hook(self):
        """ Once every module is loaded, those installed after this one too: the demo flows of the apps just
            installed, when the database has demo data. """
        super()._register_hook()
        apps = {app for app, _keys in DEMO_FLOWS.values()} | {'om_approval'}
        if apps & set(self.pool.updated_modules) and self.env['ir.module.module']._get('om_approval').demo:
            self._load_demo_flows()

    @api.model
    def _load_demo_flows(self):
        """ The templates of the apps the database has, as inactive flows to try: each app once. """
        param = self.env['ir.config_parameter'].sudo()
        done = set(filter(None, param.get_str(DEMO_PARAM).split(',')))
        # the director of the demo is the administrator, not the super user
        admin = self.env.ref('base.user_admin', raise_if_not_found=False)
        Rule = (self.with_user(admin) if admin else self).sudo()
        loaded = set()
        for model, (app, keys) in DEMO_FLOWS.items():
            if app in done or model not in self.env:
                continue
            for key in keys:
                try:
                    with self.env.cr.savepoint():
                        Rule._gallery_flow_create(key, model)
                except UserError:
                    continue  # the template does not fit this database, e.g. a button removed
            loaded.add(app)
        if loaded:
            param.set_str(DEMO_PARAM, ','.join(sorted(done | loaded)))
        return loaded

    @api.model
    def _gallery_button(self, model, method):
        button = self.env['approval.button']._sync(model).filtered(lambda b: b.method == method)[:1]
        return button.id or False

    @api.model
    def _gallery_group(self, preset):
        group = self.env.ref(preset['group'], raise_if_not_found=False) if preset.get('group') else None
        return group.id if group else self.env.ref('om_approval.group_approval_manager').id

    @api.model
    def _gallery_flow_values(self, key, model, preset):
        """ :return: the values of the flow the template `key` creates for `model` """
        label, base = preset['label'], list(preset.get('domain') or [])
        manager = {'name': self.env._('Manager'), 'approver_type': 'group', 'group_id': self._gallery_group(preset),
                   'remind_days': 1}
        if key in ('amount', 'two_level'):
            limit = preset['limit']
            values = {
                'name': self.env._('%(label)s above %(limit)s', label=label, limit=f'{limit:,}'),
                'button_id': self._gallery_button(model, preset['confirm']),
                'domain': repr(base),
                'amount_field': preset['amount'],
                'amount_min': limit,
                'step_ids': [Command.create(manager)],
            }
            if key == 'two_level':
                values['name'] = self.env._('%(label)s: two levels above %(limit)s', label=label, limit=f'{limit:,}')
                values['step_ids'].append(Command.create({
                    'name': self.env._('Director'), 'approver_type': 'user', 'user_ids': [Command.link(self.env.uid)],
                    'amount_min': preset['high_limit']}))
                values['note'] = self.env._('Above %(limit)s a manager approves; above %(high)s, the director too.',
                                            limit=f'{limit:,}', high=f'{preset["high_limit"]:,}')
            return values
        if key == 'responsible':
            path = preset.get('leader') or preset['responsible']
            return {
                'name': self.env._('%s: approval by the person responsible', label),
                'button_id': self._gallery_button(model, preset['confirm']),
                'domain': repr(base),
                'self_approve': False,
                'fallback_group_id': self._gallery_group(preset),
                'step_ids': [Command.create({'name': self.env._('Person Responsible'), 'approver_type': 'field',
                                             'field_path': path, 'remind_days': 1, 'escalate_days': 3})],
            }
        if key == 'discount':
            return {
                'name': self.env._('%(label)s with a discount above %(limit)s%%', label=label,
                                   limit=preset['discount_limit']),
                'button_id': self._gallery_button(model, preset['confirm']),
                'domain': repr(base + [(preset['discount'], '>', preset['discount_limit'])]),
                'step_ids': [Command.create(manager)],
            }
        if key == 'cancel':
            return {
                'name': self.env._('%s: approval to cancel', label),
                'button_id': self._gallery_button(model, preset['cancel']),
                'domain': repr(base + list(preset.get('cancel_domain') or [])),
                'step_ids': [Command.create(manager)],
            }
        raise UserError(self.env._('This template no longer exists.'))
