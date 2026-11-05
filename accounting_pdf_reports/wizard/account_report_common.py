from odoo import api, fields, models, _
from odoo.tools.misc import get_lang


class ReportCompanyNotice(models.AbstractModel):
    _name = "om.report.company.notice"
    _description = "Notice of the company a report covers"

    # a default and not a compute: the form opens a new record with the fields it has no dependency for left empty
    company_notice = fields.Char(string='Company Notice', readonly=True,
                                 default=lambda self: self._get_company_notice())

    def _get_report_companies(self):
        """ :return: the companies the report covers: the active one with its branches, whatever else the switcher
        has selected """
        return self.env['res.company'].browse(self.env['account.move.line']._branch_ids(self.env.company.id))

    def _get_company_notice(self):
        if not self.env.companies - self._get_report_companies():
            return False
        return _(
            'Several companies are selected, but this report only covers %(company)s, the active company. '
            'To report on another company, make it the active company.',
            company=self.env.company.name,
        )


class AccountCommonReport(models.TransientModel):
    _name = "account.common.report"
    _inherit = "om.report.company.notice"
    _description = "Account Common Report"

    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, default=lambda self: self.env.company)
    journal_ids = fields.Many2many(
        comodel_name='account.journal',
        string='Journals',
        required=True,
        # 'child_of': the journals of the company and of the branches it consolidates
        default=lambda self: self.env['account.journal'].search([('company_id', 'child_of', self.env.company.id)]),
        domain="[('company_id', 'child_of', company_id)]",
    )
    date_from = fields.Date(string='Start Date')
    date_to = fields.Date(string='End Date')
    target_move = fields.Selection([('posted', 'All Posted Entries'),
                                    ('all', 'All Entries'),
                                    ], string='Target Moves', required=True, default='posted')

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.company_id:
            self.journal_ids = self.env['account.journal'].search(
                [('company_id', 'child_of', self.company_id.id)])
        else:
            self.journal_ids = self.env['account.journal'].search([])

    def _build_contexts(self, data):
        result = {}
        result['journal_ids'] = 'journal_ids' in data['form'] and data['form']['journal_ids'] or False
        result['state'] = 'target_move' in data['form'] and data['form']['target_move'] or ''
        result['date_from'] = data['form']['date_from'] or False
        result['date_to'] = data['form']['date_to'] or False
        result['strict_range'] = True if result['date_from'] else False
        result['company_id'] = data['form']['company_id'][0] or False
        return result

    def _print_report(self, data):
        raise NotImplementedError()

    def check_report(self):
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(['date_from', 'date_to', 'journal_ids', 'target_move', 'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = dict(used_context, lang=get_lang(self.env).code)
        return self.with_context(discard_logo_check=True)._print_report(data)
