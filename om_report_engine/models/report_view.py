from odoo import api, fields, models

# what a saved view keeps besides the options the report declares; the dates
# are kept as the preset only when it is a relative one ("this month" stays
# "this month" next month)
SAVED_KEYS = ('date_preset', 'date_from', 'date_to', 'search', 'columns', 'sort', 'group_by', 'compare',
              'compare_periods')


class OmReportView(models.Model):
    """Filters, options and columns of a report, saved under a name."""
    _name = 'om.report.view'
    _description = 'Dynamic Report Saved View'
    _order = 'is_default desc, name'

    name = fields.Char(required=True)
    report_model = fields.Char(required=True, index=True, help="The model of the report the view belongs to.")
    options = fields.Json()
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, required=True, index=True,
                              ondelete='cascade')
    shared = fields.Boolean(help="Visible to every user of the company who can open the report.")
    is_default = fields.Boolean("Default", help="Opened when the report is opened.")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True,
                                 ondelete='cascade')

    @api.model
    def _om_clean_options(self, report, options):
        declared = set(report._om_default_options())
        options = {k: v for k, v in (options or {}).items() if k in declared or k in SAVED_KEYS}
        if options.get('date_preset') != 'custom':
            options.pop('date_from', None)
            options.pop('date_to', None)
        return options

    @api.model
    def om_list(self, report_model):
        self.env['om.report']._om_get_report_model(report_model)
        views = self.search([('report_model', '=', report_model)])
        mine_default = views.filtered(lambda v: v.is_default and v.user_id == self.env.user)[:1]
        return [{
            'id': view.id,
            'name': view.name,
            'options': view.options or {},
            'shared': view.shared,
            # a default of the user wins over a shared one
            'is_default': view == mine_default if mine_default else view.is_default,
            'mine': view.user_id == self.env.user,
        } for view in views]

    @api.model
    def om_save(self, report_model, name, options, shared=False, is_default=False, view_id=False):
        report = self.env['om.report']._om_get_report_model(report_model)
        values = {
            'name': name,
            'report_model': report_model,
            'options': self._om_clean_options(report, options),
            'shared': bool(shared),
            'is_default': bool(is_default),
        }
        view = self.browse(view_id).exists() if view_id else self.browse()
        if view and view.user_id == self.env.user:
            view.write(values)
        else:
            view = self.create(values)
        if view.is_default:
            (self.search([('report_model', '=', report_model), ('user_id', '=', self.env.user.id),
                          ('is_default', '=', True)]) - view).is_default = False
        return view.id

    def om_delete(self):
        self.filtered(lambda v: v.user_id == self.env.user).unlink()
        return True
