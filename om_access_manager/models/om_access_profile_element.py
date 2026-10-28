# View elements a profile removes: notebook pages, search filters, the search
# panel, whole view types and the apps of the Settings. View types are stripped
# from the action itself; the fields only a hidden Settings app holds are hidden.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ELEMENT_TYPES = [
    ('page', 'Notebook Tab'),
    ('filter', 'Search Filter or Group By'),
    ('searchpanel', 'Search Panel'),
    ('view', 'View Type'),
    ('settings', 'Settings App'),
]

SETTINGS_MODEL = 'res.config.settings'


def settings_app(node):
    """ The app of the Settings that ``node`` is, or None: in Odoo 15 an app
    is a <div class="app_settings_block" data-key="...">, not shown with o_not_app. """
    classes = (node.get('class') or '').split()
    if node.tag == 'div' and 'app_settings_block' in classes and 'o_not_app' not in classes:
        return node.get('data-key') or None
    return None

VIEW_TYPES = (
    'tree', 'form', 'kanban', 'calendar', 'pivot', 'graph', 'activity',
    'map', 'gantt', 'cohort', 'hierarchy',
)


class OmAccessProfileElement(models.Model):
    _name = 'om.access.profile.element'
    _inherit = ['om.access.history.mixin', 'om.access.condition.mixin']
    _description = 'Access Profile View Element Rule'

    def _om_history_kind(self):
        return _("view element")
    _order = 'profile_id, model, element_type, id'

    _clear_cache_name = 'default'

    profile_id = fields.Many2one(
        'om.access.profile', required=True, ondelete='cascade', index=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade')
    model = fields.Char(
        string='Technical Name', related='model_id.model', store=True, index=True)

    element_type = fields.Selection(ELEMENT_TYPES, default='page', required=True)
    element_name = fields.Char(
        string='Name',
        help="The name attribute of the tab or the filter, the view type for a "
             "view rule, or the name of the app for a Settings App rule "
             "(sale_management, stock...). Leave it empty for the search panel, "
             "which has only one per view.")
    element_label = fields.Char(string='Label')

    _sql_constraints = [
        ('unique_element', 'UNIQUE(profile_id, model_id, element_type, element_name)',
         'A profile can only carry one rule per view element.'),
    ]

    @api.constrains('element_type', 'condition')
    def _check_condition_type(self):
        for line in self:
            if (line.condition or '').strip() and line.element_type != 'page':
                raise ValidationError(_("Only a tab can be hidden under a condition."))

    @api.constrains('element_type', 'element_name', 'model_id')
    def _check_element_name(self):
        labels = dict(ELEMENT_TYPES)
        for line in self:
            if line.element_type == 'searchpanel':
                continue
            if not (line.element_name or '').strip():
                raise ValidationError(_(
                    "A '%s' rule needs a name.", labels[line.element_type]))
            if line.element_type == 'settings' and line.model_id.model != SETTINGS_MODEL:
                raise ValidationError(_("A Settings App rule belongs to the Settings."))
            if line.element_type == 'view' and line.element_name not in VIEW_TYPES:
                raise ValidationError(_(
                    "'%(name)s' is not a view type. Use one of: %(types)s",
                    name=line.element_name, types=', '.join(VIEW_TYPES)))

    @api.onchange('element_type')
    def _onchange_element_type(self):
        if self.element_type == 'settings':
            self.model_id = self.env['ir.model']._get(SETTINGS_MODEL)

    def name_get(self):
        result = []
        for line in self:
            name = (
                line.element_label or line.element_name
                or dict(ELEMENT_TYPES)[line.element_type])
            result.append((line.id, name or ''))
        return result
