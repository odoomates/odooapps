from odoo import api, fields, models

# lines remembered unfolded at most, per report and user
MAX_LINES = 2000


class OmReportFold(models.Model):
    """The lines a user left unfolded in a report: the report opens that way
    again. Each user has their own."""
    _name = 'om.report.fold'
    _description = 'Dynamic Report Folds'

    report_model = fields.Char(required=True, index=True)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, required=True, index=True,
                              ondelete='cascade')
    expanded = fields.Json(help="The ids of the unfolded lines.")

    _report_user_uniq = models.Constraint('unique(report_model, user_id)',
                                          'The folds of a report are kept once per user.')

    @api.model
    def om_get(self, report_model):
        """The lines the user left unfolded, or False when the user never folded or unfolded any."""
        fold = self.search([('report_model', '=', report_model), ('user_id', '=', self.env.uid)], limit=1)
        # an empty list is stored as nothing: a record without lines is "everything folded"
        return (fold.expanded or []) if fold else False

    @api.model
    def om_set(self, report_model, expanded):
        self.env['om.report']._om_get_report_model(report_model)
        expanded = [str(line_id) for line_id in (expanded or [])][:MAX_LINES]
        fold = self.search([('report_model', '=', report_model), ('user_id', '=', self.env.uid)], limit=1)
        if fold:
            fold.expanded = expanded
        else:
            self.create({'report_model': report_model, 'expanded': expanded})
        return True
