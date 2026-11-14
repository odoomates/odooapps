import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

STATES = [('verified', 'Verified'), ('no_data', 'Nothing Secured Yet'), ('corrupted', 'Corrupted')]


class AccountIntegrityCheck(models.Model):
    """ The result of a data inalterability check of a company, kept for the auditors: the hash chain of each
        journal recomputed, and the entries found changed since they were secured. """
    _name = 'account.integrity.check'
    _description = 'Data Inalterability Check'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    date = fields.Datetime(string='Checked On', required=True, readonly=True, default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string='Run By', readonly=True,
                              help='Empty: run by the weekly check.')
    state = fields.Selection(STATES, string='Result', required=True, readonly=True, tracking=True)
    line_ids = fields.One2many('account.integrity.check.line', 'check_id', string='Journals', readonly=True)

    @api.depends('date', 'company_id')
    def _compute_name(self):
        for check in self:
            check.name = self.env._('Check of %(date)s', date=fields.Datetime.to_string(check.date)[:10]) \
                if check.date else self.env._('New Check')

    @api.model
    def _run(self, company, scheduled=False):
        """ Check the hash chains of `company` and keep the result; the accounting administrators are asked to
            look at a corrupted result.

        :return: the check
        """
        Company = company
        if not self.env.user.has_group('account.group_account_user'):
            # the core check is for the accountants: the weekly check runs as one of the company
            accountant = self._accountant(company)
            if not accountant:
                raise UserError(self.env._(
                    'Nobody of %s has the full accounting features to check the data inalterability.',
                    company.name))
            Company = company.with_user(accountant)
        data = Company._check_hash_integrity()
        results = data.get('results') or []
        statuses = {result.get('status') for result in results}
        state = 'corrupted' if 'corrupted' in statuses else 'verified' if 'verified' in statuses else 'no_data'
        check = self.sudo().create({
            'company_id': company.id,
            'user_id': False if scheduled else self.env.user.id,
            'state': state,
            'line_ids': [fields.Command.create({
                'journal_name': result.get('journal_name'),
                'status': result.get('status') if result.get('status') in dict(STATES) else 'no_data',
                'message': result.get('msg_cover'),
                'secured_by_journal': result.get('restricted_by_hash_table') == 'V',
                'first_move_name': result.get('first_move_name'),
                'first_move_date': result.get('first_move_date'),
                'first_hash': result.get('first_hash'),
                'last_move_name': result.get('last_move_name'),
                'last_move_date': result.get('last_move_date'),
                'last_hash': result.get('last_hash'),
            }) for result in results],
        })
        if state == 'corrupted':
            check._notify_corrupted()
        return check.sudo(False)

    @api.model
    def _accountant(self, company):
        group = self.env.ref('account.group_account_user')
        return self.env['res.users'].sudo().search([
            ('group_ids', 'in', group.ids), ('company_ids', 'in', company.ids), ('share', '=', False),
        ], order='id', limit=1)

    def _notify_corrupted(self):
        managers = self.env.ref('account.group_account_manager').all_user_ids.filtered(
            lambda user: user.active and not user.share and self.company_id in user.company_ids)
        for user in managers[:5]:
            self.sudo().activity_schedule(
                'mail.mail_activity_data_todo', user_id=user.id,
                summary=self.env._('Accounting data changed after it was secured'),
                note=self.env._('The data inalterability check found journal entries changed since they were '
                                'secured. Look at the journals marked Corrupted.'))

    @api.model
    def _cron_check_integrity(self):
        for company in self.env['res.company'].search([('om_audit_weekly_check', '=', True)]):
            try:
                with self.env.cr.savepoint():
                    self._run(company, scheduled=True)
            except UserError as error:
                _logger.warning('Data inalterability check of %s not run: %s', company.name, error)

    @api.model
    def _last_check(self, company):
        return self.search([('company_id', '=', company.id)], limit=1)

    def action_run_check(self):
        """ Run a new check of the current company, and show it. """
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(self.env._('Only the accounting administrators run the data inalterability check.'))
        check = self._run(self.env.company)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': check.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }


class AccountIntegrityCheckLine(models.Model):
    _name = 'account.integrity.check.line'
    _description = 'Data Inalterability Check of a Journal'
    _order = 'id'

    check_id = fields.Many2one('account.integrity.check', required=True, ondelete='cascade', index=True)
    journal_name = fields.Char(string='Journal', readonly=True)
    status = fields.Selection(STATES, readonly=True)
    message = fields.Char(readonly=True)
    secured_by_journal = fields.Boolean(string='Secured on Posting', readonly=True,
                                        help='The journal secures its entries as soon as they are posted.')
    first_move_name = fields.Char(string='First Entry', readonly=True)
    first_move_date = fields.Char(string='First Date', readonly=True)
    first_hash = fields.Char(readonly=True)
    last_move_name = fields.Char(string='Last Entry', readonly=True)
    last_move_date = fields.Char(string='Last Date', readonly=True)
    last_hash = fields.Char(readonly=True)
