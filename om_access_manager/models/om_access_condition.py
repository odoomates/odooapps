# The condition of a field, button or tab rule: the rule applies only to the
# records for which it holds.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .conditions import ConditionError, condition_domain


class OmAccessConditionMixin(models.AbstractModel):
    _name = 'om.access.condition.mixin'
    _description = 'Condition of an Access Rule'

    condition = fields.Char(
        string='Only When',
        help="Leave empty to apply the rule always. Otherwise it applies only to the records "
             "matching this condition, written like an Odoo view condition: "
             "state == 'sale', amount_total > 1000, state in ['draft', 'sent'] and not is_company.")

    @api.constrains('condition', 'model_id')
    def _check_condition(self):
        for line in self:
            if not (line.condition or '').strip() or not line.model_id.model:
                continue
            if line.model_id.model not in self.env:
                continue
            try:
                condition_domain(line.condition, self.env[line.model_id.model], self.env.uid)
            except ConditionError as error:
                raise ValidationError(_("%(rule)s: %(error)s", rule=line.display_name,
                                        error=self.env._(error.args[0]))) from error
