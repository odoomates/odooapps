from odoo import api, fields, models


class OmBankReconciliationReport(models.TransientModel):
    _name = 'om.bank.reconciliation.report'
    _description = 'Bank Reconciliation Statement'
    _check_company_auto = True

    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True,
                                 default=lambda self: self.env.company)
    date = fields.Date(string='As at', required=True, default=fields.Date.context_today,
                       help='The reconciliation is drawn up as at the close of this day.')
    journal_ids = fields.Many2many('account.journal', string='Journals', required=True,
                                   check_company=True,
                                   domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
                                   default=lambda self: self._default_journal_ids())
    target_move = fields.Selection([('posted', 'All Posted Entries'),
                                    ('all', 'All Entries')],
                                   string='Target Moves', required=True, default='posted')
    show_details = fields.Boolean(string='Detail the Uncleared Items', default=True,
                                  help='List the items behind each total. On a busy account '
                                       'this can run to several pages.')

    @api.model
    def _default_journal_ids(self):
        """ Bank journals only.

        A cash journal has no third party to reconcile against - cash in hand is
        counted, not matched to a statement - so its section would only restate the
        ledger balance back at you. It stays selectable for the setups that do run a
        cash account against a statement, but it is not the default.
        """
        return self.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', self.env.company.id),
        ])

    @api.onchange('company_id')
    def _onchange_company_id(self):
        self.journal_ids = self._default_journal_ids()

    def action_print(self):
        self.ensure_one()
        data = {
            'form': self.read(['date', 'journal_ids', 'target_move', 'show_details', 'company_id'])[0],
        }
        # config=False: without it report_action can hand back the print-settings
        # window instead of the report itself
        return self.env.ref('om_account_reconcile.action_report_bank_reconciliation').report_action(
            self, data=data, config=False)
