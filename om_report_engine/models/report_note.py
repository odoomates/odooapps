from odoo import api, fields, models


class OmReportNote(models.Model):
    """A note on a figure of a dynamic report: its report, its line, its
    column and the period the figure is of. A note on the revenue of 2026
    follows that figure, in whichever column 2026 is shown."""
    _name = 'om.report.note'
    _description = 'Dynamic Report Note'
    _order = 'create_date, id'

    report_model = fields.Char(required=True, index=True)
    line_key = fields.Char(required=True, index=True, help="The id of the line in the report.")
    column_key = fields.Char(required=True, help="The column, without the period it is of.")
    date_from = fields.Date()
    date_to = fields.Date()
    note = fields.Text(required=True)
    user_id = fields.Many2one('res.users', string='Author', default=lambda self: self.env.user, required=True,
                              ondelete='cascade')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True,
                                 ondelete='cascade')

    def _om_values(self):
        return [{
            'id': note.id,
            'note': note.note,
            'author': note.user_id.name,
            'date': fields.Datetime.to_string(note.write_date or note.create_date),
            'mine': note.user_id.id == self.env.uid,
        } for note in self]
