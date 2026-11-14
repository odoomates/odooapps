import json

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

FORMAT = 'om_adaptive_views/1'
COPIED = ('kind', 'model', 'element', 'element_label', 'filter_domain', 'filter_context', 'evidence')


class OmAdaptTransfer(models.TransientModel):
    """ Move a tuned set of changes between databases, in one file.

    Views, actions and roles are written by their external IDs, which are the same on every
    database that has the same modules; changes for one person are not moved.
    """
    _name = 'om.adapt.transfer'
    _description = 'Move screen changes'

    mode = fields.Selection([('export', 'Export'), ('import', 'Import')], default='export', required=True)
    file = fields.Binary(attachment=False)
    filename = fields.Char()
    apply_imported = fields.Boolean(string='Apply on import', default=True)
    result = fields.Text(readonly=True)

    def _xmlid(self, record):
        return record.get_external_id().get(record.id) if record else False

    def action_export(self):
        self.ensure_one()
        rules = self.env['om.adapt.rule'].search([
            ('company_id', '=', self.env.company.id), ('state', '=', 'applied'), ('user_id', '=', False)])
        data = []
        for rule in rules:
            entry = {key: rule[key] for key in COPIED}
            entry.update(view=self._xmlid(rule.view_id), action=self._xmlid(rule.action_id),
                         group=self._xmlid(rule.group_id))
            if rule.kind == 'menu_order':
                # menus by their external IDs, as their IDs differ between databases
                Menu = self.env['ir.ui.menu'].sudo()
                menus = Menu.browse(rule._om_menu_ids()).exists()
                entry['menus'] = [xmlid for xmlid in (self._xmlid(menu) for menu in menus) if xmlid]
                entry['element'] = rule.element if not rule.element.isdigit() else \
                    self._xmlid(Menu.browse(int(rule.element)).exists())
                if not entry['element']:
                    continue
            data.append(entry)
        payload = json.dumps({'format': FORMAT, 'changes': data}, indent=2, ensure_ascii=False)
        self.write({
            'file': BinaryBytes(payload.encode(), filename='adaptive_views.json'), 'filename': 'adaptive_views.json',
            'result': self.env._("%s applied changes exported.", len(data)),
        })
        return self._reopen()

    def action_import(self):
        self.ensure_one()
        if not self.file:
            raise UserError(self.env._("Choose the file exported from the other database."))
        try:
            payload = json.loads(self.file.content)
        except (ValueError, TypeError) as error:
            raise UserError(self.env._("This is not a file exported by Adaptive Views.")) from error
        if not isinstance(payload, dict) or payload.get('format') != FORMAT:
            raise UserError(self.env._("This is not a file exported by Adaptive Views."))
        Rules = self.env['om.adapt.rule']
        kinds = dict(Rules._fields['kind'].selection)
        created, skipped = Rules.browse(), []
        for entry in payload.get('changes') or []:
            if not isinstance(entry, dict) or entry.get('kind') not in kinds or entry.get('model') not in self.env:
                skipped.append(str(entry.get('element') if isinstance(entry, dict) else entry))
                continue
            refs = {}
            for key, field in (('view', 'view_id'), ('action', 'action_id'), ('group', 'group_id')):
                if entry.get(key):
                    record = self.env.ref(entry[key], raise_if_not_found=False)
                    if not record:
                        refs = None
                        break
                    refs[field] = record.id
            if refs is None:
                skipped.append(entry.get('element') or '?')
                continue
            values = dict({key: entry.get(key) for key in COPIED}, **refs)
            if entry.get('kind') == 'menu_order':
                parent = entry.get('element')
                if parent != 'root':
                    parent = self.env.ref(parent, raise_if_not_found=False) if isinstance(parent, str) else None
                    if not parent or parent._name != 'ir.ui.menu':
                        skipped.append(str(entry.get('element_label') or '?'))
                        continue
                    values['element'] = str(parent.id)
                menus = [self.env.ref(xmlid, raise_if_not_found=False) for xmlid in entry.get('menus') or []
                         if isinstance(xmlid, str)]
                values['menu_order'] = json.dumps([menu.id for menu in menus if menu and menu._name == 'ir.ui.menu'])
            values['company_id'] = self.env.company.id
            existing = Rules.search(Rules._om_identity(self.env.company, values), limit=1)
            rule = existing or Rules.create(values)
            rule._om_log('import')
            created |= rule
        if self.apply_imported:
            created.filtered(lambda r: r.state != 'applied').action_apply()
        message = self.env._("%s changes imported.", len(created))
        if skipped:
            message += "\n" + self.env._("Left out, not found on this database: %s", ", ".join(skipped))
        self.result = message
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
            'view_mode': 'form', 'target': 'new',
        }
