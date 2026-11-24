""" Automations and access rights of a model, as the Studio shows them.

Automations are Odoo's own automation rules (base_automation): the Studio lists them,
makes new ones from ready-made triggers and actions, and tests them on a record.
Access rights are Odoo's ir.access records: permissions given to a group, and
restrictions that apply to everybody.
"""
from odoo import Command, _, api, models
from odoo.exceptions import AccessError, UserError

TRIGGERS = ('on_create', 'on_create_or_write', 'on_write', 'on_unlink', 'on_archive', 'on_unarchive',
            'on_time', 'on_time_created', 'on_time_updated', 'on_stage_set', 'on_user_set', 'on_state_set')
ACTION_KINDS = ('update', 'activity', 'email', 'note', 'followers', 'code')
OPERATIONS = ('read', 'write', 'create', 'unlink')


class OmPenStudio(models.AbstractModel):
    _inherit = 'om.pen.studio'

    # ------------------------------------------------------------------
    # automations
    # ------------------------------------------------------------------

    @api.model
    def studio_automations(self, model):
        self._check()
        if 'base.automation' not in self.env:
            return {'installed': False, 'rules': []}
        Automation = self.env['base.automation'].with_context(active_test=False)
        triggers = dict(Automation._fields['trigger']._description_selection(self.env))
        rules = Automation.search([('model_id.model', '=', model)])
        return {
            'installed': True,
            'triggers': [[key, label] for key, label in triggers.items() if key in TRIGGERS],
            'rules': [{
                'id': rule.id,
                'name': rule.name,
                'active': rule.active,
                'trigger': triggers.get(rule.trigger, rule.trigger),
                'actions': [action.name for action in rule.action_server_ids],
                'last_run': rule.last_run,
                'domain': rule.filter_domain or '',
            } for rule in rules],
            'templates': [{'id': template.id, 'name': template.name}
                          for template in self.env['mail.template'].search([('model', '=', model)])]
            if 'mail.template' in self.env else [],
            'has_mail': self._has_mail(model),
        }

    @api.model
    def studio_install_automation(self):
        self._check()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only an administrator can install apps."))
        module = self.env['ir.module.module'].sudo().search([('name', '=', 'base_automation')], limit=1)
        if not module:
            raise UserError(_("The Automation Rules app is not available on this server."))
        module.button_immediate_install()
        return True

    @api.model
    def studio_automation_create(self, model, values):
        """ A rule from a trigger and one action, made from the Studio's form. """
        self._check_admin()
        trigger = values.get('trigger')
        if trigger not in TRIGGERS:
            raise UserError(_("Pick when the automation runs."))
        model_id = self.env['ir.model']._get_id(model)
        vals = {
            'name': values.get('name') or _("New automation"),
            'model_id': model_id,
            'trigger': trigger,
            'filter_domain': values.get('domain') or False,
        }
        if trigger == 'on_write' and values.get('field'):
            field = self.env['ir.model.fields']._get(model, values['field'])
            vals['trigger_field_ids'] = [Command.set(field.ids)]
        if trigger in ('on_time', 'on_time_created', 'on_time_updated'):
            if trigger == 'on_time':
                date_field = self.env['ir.model.fields']._get(model, values.get('date_field') or '')
                if not date_field:
                    raise UserError(_("Pick the date the delay counts from."))
                vals['trg_date_id'] = date_field.id
            vals['trg_date_range'] = int(values.get('delay') or 1)
            vals['trg_date_range_type'] = values.get('delay_type') or 'day'
            if 'trg_date_range_mode' in self.env['base.automation']._fields:
                vals['trg_date_range_mode'] = values.get('delay_mode') or 'after'
        vals['action_server_ids'] = [Command.create(self._automation_action(model, model_id, values))]
        rule = self.env['base.automation'].create(vals)
        return {'id': rule.id}

    @api.model
    def _automation_action(self, model, model_id, values):
        kind = values.get('action')
        if kind not in ACTION_KINDS:
            raise UserError(_("Pick what the automation does."))
        name = values.get('action_name') or dict(
            update=_("Update a field"), activity=_("Plan an activity"), email=_("Send an email"),
            note=_("Log a note"), followers=_("Add followers"), code=_("Run code"))[kind]
        action = {'name': name, 'model_id': model_id}
        if kind == 'update':
            field = self.env['ir.model.fields']._get(model, values.get('field_to_set') or '')
            if not field:
                raise UserError(_("Pick the field to set."))
            action.update(state='object_write', update_path=field.name, evaluation_type='value',
                          value=str(values.get('value') or ''))
        elif kind == 'activity':
            action.update(state='next_activity', activity_summary=values.get('summary') or name,
                          activity_date_deadline_range=int(values.get('days') or 0),
                          activity_date_deadline_range_type='days',
                          activity_type_id=self.env.ref('mail.mail_activity_data_todo').id)
            if values.get('user_id'):
                action.update(activity_user_type='specific', activity_user_id=int(values['user_id']))
        elif kind == 'email':
            if not values.get('template_id'):
                raise UserError(_("Pick the email to send."))
            action.update(state='mail_post', template_id=int(values['template_id']))
        elif kind == 'note':
            action.update(state='log_note', log_note_note=values.get('note') or name)
        elif kind == 'followers':
            if not values.get('partner_ids'):
                raise UserError(_("Pick who follows the record."))
            action.update(state='followers', partner_ids=[Command.set([int(p) for p in values['partner_ids']])])
        elif kind == 'code':
            if not self.env.user.has_group('base.group_system'):
                raise AccessError(_("Only an administrator can write code."))
            action.update(state='code', code=values.get('code') or '')
        return action

    @api.model
    def studio_automation_update(self, rule_id, values):
        self._check_admin()
        rule = self.env['base.automation'].with_context(active_test=False).browse(int(rule_id)).exists()
        if not rule:
            raise UserError(_("This automation does not exist any more."))
        if 'active' in values:
            rule.active = bool(values['active'])
        if values.get('duplicate'):
            copy = rule.copy({'name': _("%s (copy)", rule.name), 'active': False})
            return {'id': copy.id}
        if values.get('delete'):
            rule.unlink()
        return True

    @api.model
    def studio_automation_test(self, rule_id, res_id):
        """ Run the actions of a rule on one record now, whatever its trigger. """
        self._check_admin()
        rule = self.env['base.automation'].with_context(active_test=False).browse(int(rule_id)).exists()
        record = self.env[rule.model_id.model].browse(int(res_id)).exists()
        if not rule or not record:
            raise UserError(_("Pick a record to test on."))
        for action in rule.action_server_ids:
            action.with_context(active_model=record._name, active_id=record.id, active_ids=record.ids,
                                om_pen_approved=True).run()
        return {'done': len(rule.action_server_ids), 'record': record.display_name}

    # ------------------------------------------------------------------
    # access rights
    # ------------------------------------------------------------------

    @api.model
    def studio_access(self, model):
        """ The permissions and restrictions of the model. """
        self._check_admin()
        accesses = self.env['ir.access'].sudo().with_context(active_test=False).search([('model_id.model', '=', model)])
        return [{
            'id': access.id,
            'name': access.name,
            'active': access.active,
            'group': access.group_id.display_name or False,
            'group_id': access.group_id.id or False,
            'kind': access.kind,
            'standard': access.is_standard,
            'operations': {op: bool(access['for_%s' % op]) for op in OPERATIONS},
            'domain': access.domain or '',
        } for access in accesses]

    @api.model
    def studio_access_save(self, model, values):
        """ Create or change a permission (with a group) or a restriction (without). """
        self._check_admin()
        operation = ''.join(letter for op, letter in (('create', 'c'), ('read', 'r'), ('write', 'u'), ('unlink', 'd'))
                            if (values.get('operations') or {}).get(op))
        if not operation:
            raise UserError(_("Tick at least one operation."))
        vals = {
            'operation': operation,
            'domain': values.get('domain') or False,
            'group_id': values.get('group_id') or False,
        }
        Access = self.env['ir.access'].sudo().with_context(active_test=False)
        if values.get('id'):
            access = Access.browse(int(values['id']))
            if access.is_standard:
                # a module's access is changed by switching it off and adding another one
                raise UserError(_("This access comes from a module: switch it off and add your own instead."))
            access.write(vals)
        else:
            group = self.env['res.groups'].browse(vals['group_id']) if vals['group_id'] else None
            vals.update({
                'name': values.get('name') or '%s %s' % (model, group.name if group else _("restriction")),
                'model_id': self.env['ir.model']._get_id(model),
            })
            Access.create(vals)
        return self.studio_access(model)

    @api.model
    def studio_access_toggle(self, access_id, active):
        self._check_admin()
        access = self.env['ir.access'].sudo().with_context(active_test=False).browse(int(access_id))
        access.active = bool(active)
        return self.studio_access(access.model_id.model)

    @api.model
    def studio_access_delete(self, access_id):
        self._check_admin()
        access = self.env['ir.access'].sudo().with_context(active_test=False).browse(int(access_id))
        model = access.model_id.model
        if access.is_standard:
            raise UserError(_("This access comes from a module: switch it off instead."))
        access.unlink()
        return self.studio_access(model)

    @api.model
    def studio_access_check(self, model, user_id):
        """ What a user can do on the model, and how many records they see. """
        self._check_admin()
        user = self.env['res.users'].browse(int(user_id)).exists()
        if not user:
            raise UserError(_("Pick a user."))
        records = self.env[model].with_user(user)
        result = {op: records.has_access(op) for op in OPERATIONS}
        result['count'] = records.search_count([]) if result['read'] else 0
        result['total'] = self.env[model].sudo().search_count([])
        return result

    @api.model
    def studio_create_group(self, name):
        self._check_admin()
        name = (name or '').strip()
        if not name:
            raise UserError(_("The group needs a name."))
        group = self.env['res.groups'].sudo().create({'name': name})
        # an external id, so the group can be used in views (groups=) and exported
        self.env['ir.model.data'].sudo().create({
            'module': '__custom__', 'name': 'om_pen_group_%s' % group.id,
            'model': 'res.groups', 'res_id': group.id, 'noupdate': True})
        return {'id': group.id, 'name': group.display_name, 'xmlid': '__custom__.om_pen_group_%s' % group.id}
