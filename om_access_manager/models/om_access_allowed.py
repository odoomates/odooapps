# Allowed Records ("only these journals"). A kind also filters every dependent
# model (entries, payments...); records are a Many2oneReference so the module
# depends on no business app.
import ast

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _lt


# kind: (label, model of the records, {model to filter: domain with {ids}})
ALLOWED_KINDS = {
    'journal': (_lt("Journals"), 'account.journal', {
        'account.journal': "[('id', 'in', {ids})]",
        'account.move': "[('journal_id', 'in', {ids})]",
        'account.move.line': "[('journal_id', 'in', {ids})]",
        'account.payment': "[('journal_id', 'in', {ids})]",
        'account.bank.statement': "[('journal_id', 'in', {ids})]",
        'account.bank.statement.line': "[('journal_id', 'in', {ids})]",
    }),
    'pos': (_lt("Points of Sale"), 'pos.config', {
        'pos.config': "[('id', 'in', {ids})]",
        'pos.session': "[('config_id', 'in', {ids})]",
        'pos.order': "[('config_id', 'in', {ids})]",
        'pos.payment': "[('session_id.config_id', 'in', {ids})]",
    }),
    'warehouse': (_lt("Warehouses"), 'stock.warehouse', {
        'stock.warehouse': "[('id', 'in', {ids})]",
        # operation types and locations of no warehouse (dropship, the
        # customer and vendor locations) are shared by all
        'stock.picking.type': "['|', ('warehouse_id', '=', False), ('warehouse_id', 'in', {ids})]",
        'stock.location': "['|', ('warehouse_id', '=', False), ('warehouse_id', 'in', {ids})]",
        'stock.picking': "[('picking_type_id.warehouse_id', 'in', {ids})]",
        'stock.quant': "[('location_id.warehouse_id', 'in', {ids})]",
        'stock.move': "['|', ('location_id.warehouse_id', 'in', {ids}), "
                      "('location_dest_id.warehouse_id', 'in', {ids})]",
        'stock.move.line': "['|', ('location_id.warehouse_id', 'in', {ids}), "
                           "('location_dest_id.warehouse_id', 'in', {ids})]",
    }),
    'location': (_lt("Locations"), 'stock.location', {
        # non-internal locations (customers, vendors...) stay usable
        'stock.location': "['|', ('usage', '!=', 'internal'), ('id', 'child_of', {ids})]",
        'stock.quant': "[('location_id', 'child_of', {ids})]",
        'stock.picking': "['|', ('location_id', 'child_of', {ids}), ('location_dest_id', 'child_of', {ids})]",
        'stock.move': "['|', ('location_id', 'child_of', {ids}), ('location_dest_id', 'child_of', {ids})]",
        'stock.move.line': "['|', ('location_id', 'child_of', {ids}), ('location_dest_id', 'child_of', {ids})]",
    }),
    'dashboard': (_lt("Dashboards"), 'spreadsheet.dashboard', {
        'spreadsheet.dashboard': "[('id', 'in', {ids})]",
    }),
    'team': (_lt("Sales Teams"), 'crm.team', {
        'crm.team': "[('id', 'in', {ids})]",
        'sale.order': "[('team_id', 'in', {ids})]",
        'sale.report': "[('team_id', 'in', {ids})]",
        'crm.lead': "[('team_id', 'in', {ids})]",
    }),
}


class OmAccessAllowed(models.Model):
    _name = 'om.access.allowed'
    _inherit = ['om.access.history.mixin']
    _description = 'Allowed Record'

    def _om_history_kind(self):
        return _("allowed record")

    def _om_history_label(self):
        kind = dict(self._selection_kinds()).get(self.kind, self.kind)
        return '%s: %s' % (kind, self.display_name or '')
    _order = 'id'

    # the rules are cached per user: any change here must reach them
    _clear_cache_name = 'default'

    profile_id = fields.Many2one('om.access.profile', ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', ondelete='cascade', index=True)
    kind = fields.Selection(selection='_selection_kinds', string='Allowed', required=True)
    res_model = fields.Char(compute='_compute_res_model', store=True)
    res_id = fields.Many2oneReference(string='Record', model_field='res_model')
    per_user = fields.Boolean(
        string="Each User's Own",
        help="Instead of a record, use the records of this kind set on the form of each "
             "user of the profile: one profile then serves every cashier, each on their "
             "own point of sale.")

    @api.model
    def _selection_kinds(self):
        lang = self.env.lang or 'en_US'
        return [(kind, label._translate(lang) if hasattr(label, '_translate') else str(label))
                for kind, (label, model_name, _filters) in ALLOWED_KINDS.items()
                if model_name in self.env]

    @api.depends('kind')
    def _compute_res_model(self):
        for line in self:
            line.res_model = ALLOWED_KINDS[line.kind][1] if line.kind in ALLOWED_KINDS else False

    @api.constrains('profile_id', 'user_id', 'res_id', 'per_user')
    def _check_target(self):
        for line in self:
            if bool(line.profile_id) == bool(line.user_id):
                raise ValidationError(_("An allowed record belongs to a profile or to a user."))
            if line.user_id and line.per_user:
                raise ValidationError(_("'Each user's own' is set on a profile, not on a user."))
            if not line.per_user and not line.res_id:
                raise ValidationError(_("Pick the allowed record, or tick 'Each user's own'."))

    @api.depends('res_model', 'res_id', 'per_user')
    def _compute_display_name(self):
        for line in self:
            if line.per_user:
                line.display_name = _("Each user's own")
            elif line.res_model in self.env and line.res_id:
                line.display_name = self.env[line.res_model].sudo().browse(line.res_id).display_name
            else:
                line.display_name = False

    @api.model
    def _filters(self, kind, ids):
        """ {model: domain string} restricting the models of ``kind`` to ``ids``. """
        result = {}
        ids = sorted(ids)
        for model_name, template in ALLOWED_KINDS[kind][2].items():
            if model_name not in self.env:
                continue
            model = self.env[model_name]
            # a filter on a field the installed version lacks is left out
            # rather than breaking every access check of the model
            leaves = ast.literal_eval(template.format(ids=[]))
            if all(leaf[0].split('.')[0] in model._fields
                   for leaf in leaves if isinstance(leaf, tuple)):
                result[model_name] = template.format(ids=ids)
        return result
