# Per field rules of a profile. View level only: a hidden field is removed from
# the arch the client receives, which is not the same as being unreadable.
from odoo import _, api, fields, models


class OmAccessProfileField(models.Model):
    _name = 'om.access.profile.field'
    _inherit = ['om.access.history.mixin', 'om.access.condition.mixin']
    _description = 'Access Profile Field Rule'

    def _om_history_kind(self):
        return _("field")

    def _om_history_label(self):
        mode = dict(self._fields['mode']._description_selection(self.env)).get(self.mode, self.mode)
        return '%s / %s: %s' % (self.model_id.name or '', self.field_id.field_description or '', mode)
    _order = 'profile_id, model_id, id'

    _clear_cache_name = 'default'

    profile_id = fields.Many2one(
        'om.access.profile', required=True, ondelete='cascade', index=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade')
    model = fields.Char(
        string='Technical Name', related='model_id.model', store=True, index=True)
    field_id = fields.Many2one(
        'ir.model.fields', string='Field', required=True, ondelete='cascade',
        domain="[('model_id', '=', model_id)]")
    mode = fields.Selection(
        [('hide', 'Hidden'),
         ('readonly', 'Read Only'),
         ('required', 'Required'),
         ('keep', 'Keep as is')],
        default='hide', required=True,
        help="'Keep as is' leaves the field alone and applies only the options "
             "below.")
    no_open = fields.Boolean(
        string='No External Link',
        help="Removes the arrow that opens the linked record. Relational "
             "fields only.")
    no_create = fields.Boolean(
        string='No Create from Here',
        help="Removes 'Create' and 'Create and edit' from the dropdown. "
             "Relational fields only.")
    no_export = fields.Boolean(
        string='Not Exported',
        help="Left out of the Export dialog and refused in an export, while still "
             "shown on the screens.")
    field_domain = fields.Char(
        string='Value Filter',
        help="Restricts the values the dropdown offers, and refuses another "
             "value when the record is saved. Relational fields only.")

    _unique_field = models.Constraint(
        'UNIQUE(profile_id, field_id)',
        'A profile can only carry one rule per field.',
    )

    @api.onchange('model_id')
    def _onchange_model_id(self):
        if self.field_id.model_id != self.model_id:
            self.field_id = False
