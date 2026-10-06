# New from Template: turns a recipe into an ordinary profile, applying its apps
# through the Restrict an App wizard.
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.om_access_templates import TEMPLATES, TEMPLATES_BY_KEY


class OmAccessTemplateWizard(models.TransientModel):
    _name = 'om.access.template.wizard'
    _description = 'New Access Profile from a Template'

    template_key = fields.Selection(
        selection='_selection_templates', string='Template', required=True)
    description = fields.Text(compute='_compute_template_info')
    uses = fields.Char(string='Apps', compute='_compute_template_info')
    any_app = fields.Boolean(compute='_compute_template_info')
    app_id = fields.Many2one(
        'ir.ui.menu', string='App', domain=[('parent_id', '=', False)],
        help="The app the template applies to.")
    name = fields.Char(string='Profile Name', required=True)
    user_ids = fields.Many2many('res.users', string='Users', domain=[('share', '=', False)])

    def _text(self, value):
        """ A text of a recipe, in the language of the user. """
        return value._translate(self.env.lang) if hasattr(value, '_translate') else str(value)

    @api.model
    def _available_templates(self):
        installed = self.env['ir.module.module']._installed()
        return [template for template in TEMPLATES
                if all(module in installed for module in template['requires'])]

    @api.model
    def _selection_templates(self):
        return [(template['key'], self._text(template['name'])) for template in self._available_templates()]

    @api.depends('template_key')
    def _compute_template_info(self):
        installed = self.env['ir.module.module']._installed()
        for wizard in self:
            template = TEMPLATES_BY_KEY.get(wizard.template_key)
            wizard.description = template and self._text(template['description'])
            wizard.any_app = bool(template and template.get('any_app'))
            wizard.uses = template and ', '.join(
                self._module_label(module) for module in self._template_modules(template)
                if module in installed) or False

    @api.onchange('template_key', 'app_id')
    def _onchange_name(self):
        template = TEMPLATES_BY_KEY.get(self.template_key)
        if not template:
            return
        name = self._text(template['name'])
        if template.get('any_app') and self.app_id:
            name = '%s: %s' % (self.app_id.name, name)
        self.name = name

    @api.model
    def _template_modules(self, template):
        """ The modules a recipe touches, in order: what it requires, then the
        modules of its app parts. """
        modules = list(template['requires'])
        for part in template.get('apps', ()):
            if part['app']:
                module = part['app'].split('.')[0]
                if module not in modules:
                    modules.append(module)
        return modules

    @api.model
    def _module_label(self, module_name):
        module = self.env['ir.module.module'].sudo().search([('name', '=', module_name)], limit=1)
        return module.shortdesc or module_name

    #
    # building the profile
    #

    def action_create(self):
        self.ensure_one()
        template = TEMPLATES_BY_KEY.get(self.template_key)
        if not template or template not in self._available_templates():
            raise UserError(_("This template needs an app that is not installed."))
        if template.get('any_app') and not self.app_id:
            raise UserError(_("Pick the app this template applies to."))
        profile = self.env['om.access.profile'].create(dict(
            template.get('switches', {}),
            name=self.name,
            user_ids=[(6, 0, self.user_ids.ids)],
        ))
        notes = self._apply_template(profile, template)
        profile.note = self._note(template, notes)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'om.access.profile',
            'res_id': profile.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _apply_template(self, profile, template):
        """ Apply every part of the recipe to ``profile``; return what was skipped. """
        installed = self.env['ir.module.module']._installed()
        notes = []

        for part in template.get('apps', ()):
            if part['app'] is None:
                app = self.app_id
            else:
                app = self.env.ref(part['app'], raise_if_not_found=False)
                if not app:
                    module = part['app'].split('.')[0]
                    if module not in installed:
                        notes.append(_("%s is not installed: its part was skipped.",
                                       self._module_label(module)))
                    else:
                        notes.append(_("The app menu %s was not found: its part was skipped.",
                                       part['app']))
                    continue
            wizard = self.env['om.access.app.wizard'].create({
                'profile_id': profile.id,
                'app_id': app.id,
                'level': part['level'],
                'own_records': part.get('own_records', False),
            })
            wizard._load_lines()
            wizard._apply_level()
            wizard.action_apply()

        rows = {row.model: row for row in profile.model_ids}
        for model_name, perms in template.get('models', {}).items():
            if model_name not in self.env:
                continue
            if model_name in rows:
                rows[model_name].write(perms)
            else:
                self.env['om.access.profile.model'].create(dict(
                    perms, profile_id=profile.id, model_id=self.env['ir.model']._get(model_name).id))

        menus = self.env['ir.ui.menu']
        for xmlid in template.get('hide_menus', ()):
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                menus |= menu
            elif xmlid.split('.')[0] in installed:
                notes.append(_("The menu %s was not found and stays visible.", xmlid))
        if menus:
            profile.hidden_menu_ids = profile.hidden_menu_ids | menus

        field_lines = []
        for model_name, field_name, mode in template.get('fields', ()):
            if model_name not in self.env:
                continue
            field = self.env['ir.model.fields']._get(model_name, field_name)
            if not field:
                notes.append(_("The field %(field)s of %(model)s was not found and stays visible.",
                               field=field_name, model=model_name))
                continue
            field_lines.append({
                'profile_id': profile.id,
                'model_id': field.model_id.id,
                'field_id': field.id,
                'mode': mode,
            })
        if field_lines:
            self.env['om.access.profile.field'].create(field_lines)
        return notes

    def _note(self, template, notes):
        note = Markup('<p>%s</p><p>%s</p>') % (
            _("Created from the template %s.", self._text(template['name'])),
            self._text(template['description']))
        if notes:
            note += Markup('<p>%s</p><ul>%s</ul>') % (
                _("Skipped:"), Markup('').join(Markup('<li>%s</li>') % escape(text) for text in notes))
        return note
