# Per button rules of a profile. button_id tells apart buttons sharing a name.
# Blocking only knows the model and method, so view_type and button_id narrow
# the hiding, never the blocking.
from odoo import _, api, fields, models


class OmAccessProfileButton(models.Model):
    _name = 'om.access.profile.button'
    _inherit = ['om.access.history.mixin', 'om.access.condition.mixin']
    _description = 'Access Profile Button Rule'

    def _om_history_kind(self):
        return _("button")

    def _om_history_label(self):
        return '%s: %s' % (self.model_id.name or '', self.display_name or '')
    _order = 'profile_id, model, button_label, id'

    _clear_cache_name = 'default'

    profile_id = fields.Many2one(
        'om.access.profile', required=True, ondelete='cascade', index=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade')
    model = fields.Char(
        string='Technical Name', related='model_id.model', store=True, index=True)

    view_type = fields.Selection(
        [('any', 'Any View'), ('form', 'Form'), ('tree', 'List'), ('kanban', 'Kanban')],
        default='any', required=True)
    button_type = fields.Selection(
        [('object', 'Method'), ('action', 'Action')],
        default='object', required=True)
    button_name = fields.Char(
        string='Button', required=True,
        help="The method the button calls, or the id of the action it opens.")
    button_id = fields.Char(
        string='Button Id',
        help="The id attribute of the button in the view. Leave it empty to "
             "match every button calling the same method.")
    button_label = fields.Char(string='Label')

    mode = fields.Selection(
        [('hide', 'Hide only'),
         ('block', 'Block only'),
         ('hide_block', 'Hide and block')],
        default='hide_block', required=True,
        help="Hiding removes the button from the screen, which a crafted call "
             "can still work around. Blocking refuses the call on the server. "
             "Keep both unless you have a reason not to.")

    _sql_constraints = [
        ('unique_button', 'UNIQUE(profile_id, model_id, view_type, button_type, button_name, button_id)',
         'A profile can only carry one rule per button.'),
    ]

    @api.depends('button_label', 'button_name')
    def _compute_display_name(self):
        for line in self:
            line.display_name = line.button_label or line.button_name or ''
