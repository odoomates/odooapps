from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OmDeferredReport(models.TransientModel):
    """ The Deferred Revenue and Deferred Expense reports: what the deferred lines recognise before,
    in and after a period. """
    _name = 'om.deferred.report'
    _description = 'Deferred Revenue and Expense Report'

    kind = fields.Selection(
        [('expense', 'Deferred Expense'), ('revenue', 'Deferred Revenue')], required=True,
        default=lambda self: self.env.context.get('default_kind', 'expense'))
    date_from = fields.Date(string='Start Date', required=True,
                            default=lambda self: fields.Date.start_of(fields.Date.context_today(self), 'month'))
    date_to = fields.Date(string='End Date', required=True,
                          default=lambda self: fields.Date.end_of(fields.Date.context_today(self), 'month'))
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    generation = fields.Selection(
        [('on_post', 'On validation'), ('manual', 'Manually & Grouped')], compute='_compute_generation')
    line_ids = fields.One2many('om.deferred.report.line', 'report_id', string='Lines')

    @api.depends('kind', 'company_id')
    def _compute_generation(self):
        for report in self:
            report.generation = report.company_id._om_deferred_settings(report.kind)['generation']

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for report in self:
            if report.date_from > report.date_to:
                raise UserError(_("The start date of the report comes after its end date."))

    def _title(self):
        return dict(self._fields['kind'].selection)[self.kind]

    def _compute_lines(self):
        self.ensure_one()
        self.line_ids.unlink()
        values = []
        sign = 1 if self.kind == 'expense' else -1
        for line in self.env['account.move.line']._om_deferred_lines(self.kind, grouped_only=False):
            split = line._om_deferral_split(self.date_from, self.date_to)
            values.append({
                'report_id': self.id,
                'move_line_id': line.id,
                **{key: sign * amount for key, amount in split.items()},
            })
        self.env['om.deferred.report.line'].create(values)

    def action_show(self):
        self.ensure_one()
        self._compute_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': _("%(report)s: %(start)s to %(end)s", report=self._title(),
                      start=self.date_from, end=self.date_to),
            'res_model': 'om.deferred.report.line',
            'view_mode': 'list',
            'domain': [('report_id', '=', self.id)],
            'context': {'search_default_group_account': 1, 'create': False, 'edit': False, 'delete': False},
        }

    def action_print(self):
        self.ensure_one()
        self._compute_lines()
        return self.env.ref('om_account_deferred.action_report_deferred').report_action(self)

    def action_generate(self):
        """ Manually & Grouped: the entry of the period and its reversal. """
        self.ensure_one()
        if self.generation != 'manual':
            raise UserError(_(
                "The deferral entries are generated on the validation of each invoice and bill. Choose "
                "Manually & Grouped in the accounting settings to generate them from this report."))
        moves = self.env['account.move']._om_grouped_deferral(self.kind, self.date_to)
        return {
            'type': 'ir.actions.act_window',
            'name': _("Deferral Entries"),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
            'context': {'create': False},
        }


class OmDeferredReportLine(models.TransientModel):
    _name = 'om.deferred.report.line'
    _description = 'Deferred Revenue and Expense Report Line'
    _order = 'account_id, start_date, id'

    report_id = fields.Many2one('om.deferred.report', required=True, ondelete='cascade')
    move_line_id = fields.Many2one('account.move.line', string='Journal Item', required=True, ondelete='cascade')
    move_id = fields.Many2one(related='move_line_id.move_id', string='Document')
    account_id = fields.Many2one(related='move_line_id.account_id', store=True)
    partner_id = fields.Many2one(related='move_line_id.partner_id')
    name = fields.Text(related='move_line_id.name', string='Label')
    start_date = fields.Date(related='move_line_id.om_deferred_start_date', store=True)
    end_date = fields.Date(related='move_line_id.om_deferred_end_date')
    currency_id = fields.Many2one(related='move_line_id.company_currency_id')
    total = fields.Monetary(currency_field='currency_id')
    not_started = fields.Monetary(currency_field='currency_id')
    before = fields.Monetary(currency_field='currency_id')
    current = fields.Monetary(currency_field='currency_id')
    later = fields.Monetary(currency_field='currency_id')

    def action_open_document(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
        }
