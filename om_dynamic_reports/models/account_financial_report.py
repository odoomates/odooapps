from odoo import fields, models


class AccountFinancialReport(models.Model):
    _inherit = 'account.financial.report'

    dynamic_date_mode = fields.Selection([
        ('range', "Over a period"),
        ('as_of', "At a date"),
    ], string="Dates", default='range', required=True,
        help="Over a period, as a profit and loss is; at a date, from the beginning up to it, as a balance "
             "sheet is.")
    dynamic_total = fields.Boolean(string="Total Line", default=True,
                                   help="End the report with the amount of the report itself, as the net "
                                        "profit ends a profit and loss.")

    dynamic_action_id = fields.Many2one('ir.actions.client', string="Dynamic Report Action", readonly=True,
                                        copy=False, ondelete='set null')

    def action_open_report(self):
        """ The report on screen, with its filters, instead of the PDF wizard. """
        self.ensure_one()
        model = 'om.dynamic.report.custom.as.of' if self.dynamic_date_mode == 'as_of' \
            else 'om.dynamic.report.custom'
        values = {
            'name': self.name,
            'tag': 'om_report',
            'context': repr({'om_report_model': model, 'om_report_variant': self.id}),
        }
        # a stored action, so that the page opens again on a reload of the browser
        action = self.sudo().dynamic_action_id
        if action:
            action.write(values)
        else:
            action = self.env['ir.actions.client'].sudo().create(values)
            self.sudo().dynamic_action_id = action
        return action._get_action_dict()

    def _remove_menu(self):
        actions = self.sudo().dynamic_action_id
        super()._remove_menu()
        self.sudo().dynamic_action_id = False
        actions.unlink()
