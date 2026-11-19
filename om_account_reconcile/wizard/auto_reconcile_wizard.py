from odoo import fields, models, _
from odoo.exceptions import UserError


class OmAutoReconcileWizard(models.TransientModel):
    _name = 'om.auto.reconcile.wizard'
    _description = 'Reconcile Journal Items Automatically'
    _check_company_auto = True

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    mode = fields.Selection([
        ('one_to_one', 'Perfect pairs: an item and another of the opposite amount'),
        ('zero_balance', 'Clear the balance: all the items of a partner adding up to zero'),
    ], string='Reconcile', required=True, default='one_to_one')
    account_ids = fields.Many2many(
        'account.account', string='Accounts', check_company=True, domain=[('reconcile', '=', True)],
        help='Leave empty for every account allowing reconciliation.')
    partner_ids = fields.Many2many('res.partner', string='Partners', help='Leave empty for every partner.')
    date_from = fields.Date(string='From')
    date_to = fields.Date(string='To')

    def _domain(self):
        self.ensure_one()
        domain = [('company_id', 'child_of', self.company_id.id)]
        if self.account_ids:
            domain.append(('account_id', 'in', self.account_ids.ids))
        if self.partner_ids:
            domain.append(('partner_id', 'child_of', self.partner_ids.ids))
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))
        return domain

    def action_reconcile(self):
        self.ensure_one()
        AccountMoveLine = self.env['account.move.line']
        groups = AccountMoveLine._om_suggest_item_matches(self._domain(), limit=1000, mode=self.mode)
        if not groups:
            raise UserError(_('Nothing to reconcile with these criteria.'))
        for lines in groups:
            lines._om_reconcile_items()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('%s group(s) of journal items reconciled.', len(groups)),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
