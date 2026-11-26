from datetime import timedelta

from odoo import api, fields, models

LOG_RETENTION_DAYS = 180


class BankFeedLog(models.Model):
    _name = 'bank.feed.log'
    _description = 'Bank Feed Sync Log'
    _order = 'id desc'

    connection_id = fields.Many2one(
        'bank.feed.connection', string='Connection', required=True, index=True, ondelete='cascade')
    account_id = fields.Many2one('bank.feed.account', string='Bank Account', index='btree_not_null',
                                 ondelete='set null')
    journal_id = fields.Many2one(related='account_id.journal_id', string='Journal')
    company_id = fields.Many2one(related='connection_id.company_id', store=True, index=True)
    level = fields.Selection([
        ('info', 'Done'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ], string='Result', required=True, default='info')
    date_from = fields.Date(string='Read From')
    imported_count = fields.Integer(string='Imported')
    skipped_count = fields.Integer(string='Already Imported')
    pending_count = fields.Integer(string='Pending')
    message = fields.Text(string='Message')

    @api.autovacuum
    def _gc_old_logs(self):
        self.search([('create_date', '<', fields.Datetime.now() - timedelta(days=LOG_RETENTION_DAYS))]).unlink()
