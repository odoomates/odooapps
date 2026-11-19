from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval


class OmReportHorizontalGroup(models.Model):
    """Columns a report splits its amounts in: one per value of the fields of
    the rules (one per combination of values with several rules), as found in
    the journal items of the report."""
    _name = 'om.report.horizontal.group'
    _description = 'Report Horizontal Group'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string="Company",
                                 help="Leave empty to offer the group in every company.")
    report_model_ids = fields.Many2many(
        'ir.model', string="Reports",
        domain=lambda self: [('model', 'in', self._odr_horizontal_report_models())],
        help="The reports offering the group; leave empty for all of them.")
    rule_ids = fields.One2many('om.report.horizontal.group.rule', 'group_id', string="Rules", copy=True)

    @api.model
    def _odr_horizontal_report_models(self):
        """The reports that can split their amounts by a horizontal group."""
        return sorted(name for name in self.env.registry.descendants(['om.dynamic.report'], '_inherit')
                      if self.env[name]._report_name and getattr(self.env[name], '_odr_horizontal', False))

    def _odr_applies_to(self, model_name):
        self.ensure_one()
        return not self.report_model_ids or model_name in self.report_model_ids.mapped('model')


class OmReportHorizontalGroupRule(models.Model):
    """A field of the journal items whose values make the columns; the domain
    keeps some of its values only."""
    _name = 'om.report.horizontal.group.rule'
    _description = 'Report Horizontal Group Rule'
    _order = 'sequence, id'

    group_id = fields.Many2one('om.report.horizontal.group', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    field_id = fields.Many2one(
        'ir.model.fields', string="Field", required=True, ondelete='cascade',
        domain=[('model', '=', 'account.move.line'), ('ttype', '=', 'many2one'), ('store', '=', True),
                ('name', 'not in', ('id', 'create_uid', 'write_uid'))],
        help="The journal items are split by the values of this field.")
    relation = fields.Char(related='field_id.relation')
    domain = fields.Char(string="Values", default='[]',
                         help="Only the values matching this domain get a column.")

    def _odr_domain(self):
        self.ensure_one()
        return list(Domain(safe_eval(self.domain or '[]')))
