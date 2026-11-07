from odoo import api, fields, models

# what a saved view keeps of the options; the dates are kept as the preset only
# when it is a relative one ("this month" stays "this month" next month)
SAVED_KEYS = (
    'date_preset', 'date_from', 'date_to', 'warehouse_ids', 'location_ids', 'product_ids', 'category_ids',
    'lot_ids', 'owner_ids', 'partner_ids', 'picking_type_ids', 'child_locations', 'hide_zero', 'group_by',
    'columns', 'sort', 'search', 'kpi_filter', 'compare',
)


class OmInventoryReportView(models.Model):
    """Filters, grouping and columns of a report, saved under a name."""
    _name = 'om.inventory.report.view'
    _description = 'Inventory Report Saved View'
    _order = 'is_default desc, name'

    name = fields.Char(required=True)
    report_key = fields.Char(required=True, index=True)
    options = fields.Json()
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, required=True, index=True,
                              ondelete='cascade')
    shared = fields.Boolean(help="Visible to every Inventory user of the company.")
    is_default = fields.Boolean("Default", help="Opened when the report is opened.")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True,
                                 ondelete='cascade')

    @api.model
    def _om_clean_options(self, report_key, options):
        report = self.env['om.inventory.report']._om_report(report_key)
        extra = tuple(report._report_extra_options)
        options = {k: v for k, v in (options or {}).items() if k in SAVED_KEYS + extra}
        if options.get('date_preset') != 'custom':
            options.pop('date_from', None)
            options.pop('date_to', None)
        return options

    @api.model
    def om_list(self, report_key):
        views = self.search([('report_key', '=', report_key)])
        return [{
            'id': view.id,
            'name': view.name,
            'options': view.options or {},
            'shared': view.shared,
            'is_default': view.is_default,
            'mine': view.user_id == self.env.user,
        } for view in views]

    @api.model
    def om_save(self, report_key, name, options, shared=False, is_default=False, view_id=False):
        self.env['om.inventory.report']._om_check_access()
        values = {
            'name': name,
            'report_key': report_key,
            'options': self._om_clean_options(report_key, options),
            'shared': bool(shared),
            'is_default': bool(is_default),
        }
        view = self.browse(view_id).exists() if view_id else self.browse()
        if view and view.user_id == self.env.user:
            view.write(values)
        else:
            view = self.create(values)
        if view.is_default:
            (self.search([('report_key', '=', report_key), ('user_id', '=', self.env.user.id),
                          ('is_default', '=', True)]) - view).is_default = False
        return view.id

    def om_delete(self):
        self.filtered(lambda v: v.user_id == self.env.user).unlink()
        return True
