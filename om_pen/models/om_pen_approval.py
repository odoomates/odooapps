""" Approvals on buttons.

A rule says that a button of a model only runs once someone approved it: a member of a
group, or a given user, and possibly only for the records matching a condition. The
check is made on the server when the button is clicked, so it cannot be skipped from
the browser.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval

APPROVAL_ACTION_TAG = 'om_pen.approval'


class OmPenApprovalRule(models.Model):
    _name = 'om.pen.approval.rule'
    _description = "Approval Rule On A Button"
    _order = 'model, button_name, sequence, id'

    name = fields.Char(string="Description", required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    model = fields.Char(required=True, index=True)
    button_name = fields.Char(string="Button", required=True,
                              help="The method of an object button, or the id of the action of an action button.")
    button_type = fields.Selection([('object', "Method"), ('action', "Action")], default='object', required=True)
    button_string = fields.Char(string="Button Label")
    group_id = fields.Many2one('res.groups', string="Approved By Group", ondelete='cascade')
    user_id = fields.Many2one('res.users', string="Approved By User", ondelete='cascade')
    domain = fields.Char(string="Only For Records", default='[]',
                         help="The rule applies to the records matching this condition only.")
    entry_ids = fields.One2many('om.pen.approval.entry', 'rule_id', string="Decisions")

    @api.constrains('group_id', 'user_id')
    def _check_approver(self):
        for rule in self:
            if not rule.group_id and not rule.user_id:
                raise UserError(_("An approval rule needs a group or a user to approve."))

    def _approver_label(self):
        self.ensure_one()
        return self.user_id.name if self.user_id else self.group_id.display_name

    def _applies_to(self, record):
        self.ensure_one()
        domain = safe_eval(self.domain or '[]', {'uid': self.env.uid, 'user': self.env.user})
        return bool(record.sudo().filtered_domain(Domain(domain)))

    def _can_approve(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        if self.user_id:
            return self.user_id == user
        return self.group_id in user.all_group_ids

    @api.model
    def _rules_for(self, model, button_name, button_type=None):
        domain = [('model', '=', model), ('button_name', '=', str(button_name))]
        if button_type:
            domain.append(('button_type', '=', button_type))
        return self.sudo().search(domain)

    @api.model
    def _missing(self, model, button_name, ids, button_type=None):
        """ (record, rule, decision) for every approval still missing on `ids`.

        A rejection keeps blocking: the decision is given so it can be shown.
        """
        rules = self._rules_for(model, button_name, button_type)
        if not rules:
            return []
        Entry = self.env['om.pen.approval.entry'].sudo()
        missing = []
        for record in self.env[model].sudo().browse(ids).exists():
            for rule in rules:
                if not rule._applies_to(record):
                    continue
                entry = Entry.search([('rule_id', '=', rule.id), ('res_id', '=', record.id)],
                                     order='id desc', limit=1)
                if not entry or entry.state != 'approved':
                    missing.append((record, rule, entry))
        return missing

    @api.model
    def _blocked_action(self, model, button_name, ids, button_type=None):
        """ The dialog to show instead of running the button, or None to let it run. """
        missing = self._missing(model, button_name, ids, button_type)
        if not missing:
            return None
        record = missing[0][0]
        return {
            'type': 'ir.actions.client',
            'tag': APPROVAL_ACTION_TAG,
            'target': 'new',
            'name': _("Approval needed"),
            'params': {'model': model, 'res_id': record.id, 'button_name': str(button_name),
                       'button_type': button_type or 'object'},
        }

    @api.model
    def approval_status(self, model, res_id, button_name, button_type=None):
        """ What the approval dialog shows for one record and one button. """
        record = self.env[model].browse(int(res_id)).exists()
        record.check_access('read')
        Entry = self.env['om.pen.approval.entry'].sudo()
        rules = []
        for rule in self._rules_for(model, button_name, button_type):
            if not rule._applies_to(record):
                continue
            entry = Entry.search([('rule_id', '=', rule.id), ('res_id', '=', record.id)], order='id desc', limit=1)
            rules.append({
                'id': rule.id,
                'name': rule.name,
                'approver': rule._approver_label(),
                'state': entry.state or 'waiting',
                'user': entry.user_id.name or '',
                'date': entry.create_date,
                'can_approve': rule._can_approve(),
            })
        return {'record': record.display_name, 'button': button_name, 'rules': rules}

    @api.model
    def approval_decide(self, rule_id, res_id, approved):
        rule = self.sudo().browse(int(rule_id)).exists()
        if not rule:
            raise UserError(_("This approval rule does not exist any more."))
        if not rule._can_approve():
            raise UserError(_("Only %s can decide on this approval.", rule._approver_label()))
        record = self.env[rule.model].browse(int(res_id)).exists()
        record.check_access('read')
        self.env['om.pen.approval.entry'].sudo().create({
            'rule_id': rule.id,
            'res_id': record.id,
            'user_id': self.env.uid,
            'state': 'approved' if approved else 'rejected',
        })
        if hasattr(record, 'message_post'):
            body = _("%(rule)s: %(decision)s by %(user)s.", rule=rule.name,
                     decision=_("approved") if approved else _("rejected"), user=self.env.user.name)
            record.sudo().message_post(body=body, subtype_xmlid='mail.mt_note')
        return True

    @api.model
    def approval_request(self, rule_id, res_id):
        """ Ask the approver, with an activity when the record can hold one. """
        rule = self.sudo().browse(int(rule_id)).exists()
        record = self.env[rule.model].browse(int(res_id)).exists()
        record.check_access('read')
        approver = rule.user_id or rule.group_id.all_user_ids.filtered(lambda u: not u.share)[:1]
        if not approver:
            raise UserError(_("Nobody can approve %s yet.", rule.name))
        if hasattr(record, 'activity_schedule'):
            record.sudo().activity_schedule(
                'mail.mail_activity_data_todo', user_id=approver.id,
                summary=_("Approve: %s", rule.name),
                note=_("%(user)s asks for your approval.", user=self.env.user.name))
        elif hasattr(record, 'message_post'):
            record.sudo().message_post(body=_("%(user)s asks %(approver)s to approve: %(rule)s.",
                                              user=self.env.user.name, approver=approver.name, rule=rule.name),
                                       partner_ids=approver.partner_id.ids)
        else:
            raise UserError(_("This record can neither hold an activity nor a message: ask %s directly.",
                              approver.name))
        return True

    @api.model
    def approval_buttons(self, model):
        """ The buttons of a model that need an approval, to mark them on screen. """
        return [{'name': rule.button_name, 'type': rule.button_type, 'approver': rule._approver_label()}
                for rule in self.sudo().search([('model', '=', model)])]


class OmPenApprovalEntry(models.Model):
    _name = 'om.pen.approval.entry'
    _description = "Approval Decision"
    _order = 'id desc'

    rule_id = fields.Many2one('om.pen.approval.rule', required=True, ondelete='cascade', index=True)
    model = fields.Char(related='rule_id.model', store=True)
    res_id = fields.Many2oneReference(string="Record", model_field='model', required=True, index=True)
    user_id = fields.Many2one('res.users', string="Decided By", required=True)
    state = fields.Selection([('approved', "Approved"), ('rejected', "Rejected")], required=True)


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    def run(self):
        """ A server action run from a button that needs an approval waits for it. """
        context = self.env.context
        model = context.get('active_model')
        ids = context.get('active_ids') or ([context['active_id']] if context.get('active_id') else [])
        if len(self) == 1 and model and ids and not context.get('om_pen_approved'):
            blocked = self.env['om.pen.approval.rule']._blocked_action(model, self.id, ids, 'action')
            if blocked:
                return blocked
        return super().run()


class OmPenStudio(models.AbstractModel):
    _inherit = 'om.pen.studio'

    @api.model
    def studio_approval_rules(self, model):
        self._check()
        rules = self.env['om.pen.approval.rule'].with_context(active_test=False).search([('model', '=', model)])
        return [{
            'id': rule.id, 'name': rule.name, 'active': rule.active, 'button_name': rule.button_name,
            'button_type': rule.button_type, 'button_string': rule.button_string or rule.button_name,
            'approver': rule._approver_label(), 'group_id': rule.group_id.id, 'user_id': rule.user_id.id,
            'domain': rule.domain or '[]',
            'decisions': len(rule.entry_ids),
        } for rule in rules]

    @api.model
    def studio_approval_buttons(self, model):
        """ The buttons of the model's form, for picking the one to approve. """
        self._check()
        from lxml import etree
        arch = etree.fromstring(self.env[model].get_view(view_type='form')['arch'])
        buttons, seen = [], set()
        for node in arch.xpath('//button[@name][@type]'):
            key = (node.get('name'), node.get('type'))
            if node.get('type') not in ('object', 'action') or key in seen or node.xpath('ancestor::field'):
                continue
            seen.add(key)
            buttons.append({'name': node.get('name'), 'type': node.get('type'),
                            'string': node.get('string') or node.get('name')})
        return buttons

    @api.model
    def studio_approval_save(self, model, values):
        self._check_admin()
        vals = {
            'model': model,
            'name': values.get('name') or _("Approval of %s", values.get('button_string') or values.get('button_name')),
            'button_name': values.get('button_name'),
            'button_type': values.get('button_type') or 'object',
            'button_string': values.get('button_string') or False,
            'group_id': values.get('group_id') or False,
            'user_id': values.get('user_id') or False,
            'domain': values.get('domain') or '[]',
        }
        if not vals['button_name']:
            raise UserError(_("Pick the button that needs an approval."))
        if vals['button_type'] == 'action' and not vals['button_name'].isdigit():
            # an action button named by external id runs the action of that id
            vals['button_name'] = str(self.env.ref(vals['button_name']).id)
        Rule = self.env['om.pen.approval.rule'].with_context(active_test=False)
        if values.get('id'):
            Rule.browse(int(values['id'])).write(vals)
        else:
            Rule.create(vals)
        return self.studio_approval_rules(model)

    @api.model
    def studio_approval_toggle(self, rule_id, active):
        self._check_admin()
        rule = self.env['om.pen.approval.rule'].with_context(active_test=False).browse(int(rule_id))
        rule.active = bool(active)
        return self.studio_approval_rules(rule.model)

    @api.model
    def studio_approval_delete(self, rule_id):
        self._check_admin()
        rule = self.env['om.pen.approval.rule'].with_context(active_test=False).browse(int(rule_id))
        model = rule.model
        rule.unlink()
        return self.studio_approval_rules(model)

    @api.model
    def studio_users(self):
        self._check()
        return [{'id': user.id, 'name': user.name} for user in self.env['res.users'].search([('share', '=', False)])]
