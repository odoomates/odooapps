from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

METHOD = 'action_post'


class AccountMove(models.Model):
    _inherit = 'account.move'

    om_approval_waiting = fields.Boolean(
        string='Waiting for Approval', compute='_compute_om_approval_waiting',
        search='_search_om_approval_waiting')

    def _om_waiting_ids(self):
        return self.env['approval.request'].sudo().search([
            ('res_model', '=', self._name), ('method', '=', METHOD), ('state', '=', 'to_approve'),
            ('res_id', 'in', self.ids),
        ]).mapped('res_id') if self.ids else []

    def _compute_om_approval_waiting(self):
        waiting = set(self._om_waiting_ids())
        for move in self:
            move.om_approval_waiting = move.id in waiting

    def _om_approval_exempt(self):
        """ The entries Odoo makes and posts itself never wait for an approval: those of the payments, the bank
            statements, the cash basis taxes, the exchange differences, the cancelling reversals, the depreciation of
            the assets and the journals posting without approval. """
        self.ensure_one()
        if self.env.context.get('move_reverse_cancel'):
            return True
        if self.origin_payment_id or self.statement_line_id or self.tax_cash_basis_rec_id \
                or self.tax_cash_basis_origin_move_id:
            return True
        if self.journal_id.om_skip_approval:
            return True
        if self.move_type == 'entry' and self.journal_id == self.company_id.currency_exchange_journal_id:
            return True
        # the depreciation entries of Asset Management, when installed
        if 'depreciation_asset_id' in self._fields and self.depreciation_asset_id:
            return True
        return False

    def _post(self, soft=True):
        """ The entries waiting for an approval are not posted, whatever posts them: the Post button and action,
            the Confirm Entries wizard, the auto-post. The auto-post leaves them aside and asks for their approval. """
        if self.env.context.get('om_approval_bypass'):
            return super()._post(soft)
        Request = self.env['approval.request']
        candidates = self.filtered(lambda move: move.state == 'draft' and not move._om_approval_exempt())
        blocked, released = Request._om_check_server(candidates, METHOD)
        moves = self
        if blocked:
            if not self.env.context.get('om_approval_autopost'):
                raise UserError(Request._om_blocked_message(blocked, METHOD))
            blocked._om_approval_autopost_hold()
            moves = self - blocked
        try:
            return super(AccountMove, moves.with_context(om_approval_autopost_skip=False))._post(soft)
        finally:
            Request._restore_lock(released)

    def _om_approval_autopost_hold(self):
        """ The auto-post found these entries waiting for an approval: it asks for it, or stops auto-posting them
            once it is refused or withdrawn. """
        Request, Rule = self.env['approval.request'], self.env['approval.rule']
        for move in self:
            request = Request._om_last_request(move, METHOD)
            if request.state == 'to_approve':
                continue
            if request.state in ('refused', 'cancel'):
                move.auto_post = 'no'
                move.message_post(body=self.env._(
                    'Auto-post stopped: the approval %s was refused or withdrawn. Post the entry by hand to ask '
                    'for it again.', request.name))
                continue
            flow = Rule._get_flow(move, METHOD)
            if flow:
                Request._request(move, flow, method=METHOD, button_name=flow.button_id.name, note=self.env._(
                    'Asked by the auto-post of the entry, dated %s.', move.date))

    @api.model
    def _autopost_draft_entries(self, batch_size=100):
        """ The entries waiting for an approval are left out of the batches, so that they do not hold the others
            back. """
        waiting = self.env['approval.request'].sudo().search([
            ('res_model', '=', self._name), ('method', '=', METHOD), ('state', '=', 'to_approve'),
        ]).mapped('res_id')
        return super(AccountMove, self.with_context(
            om_approval_autopost=True, om_approval_autopost_skip=waiting,
        ))._autopost_draft_entries(batch_size=batch_size)

    @api.model
    def _search(self, domain, *args, **kwargs):
        skip = self.env.context.get('om_approval_autopost_skip')
        if skip:
            domain = Domain(domain) & Domain('id', 'not in', skip)
        return super()._search(domain, *args, **kwargs)

    def _search_om_approval_waiting(self, operator, value):
        ids = self.env['approval.request'].sudo().search([
            ('res_model', '=', self._name), ('method', '=', METHOD), ('state', '=', 'to_approve'),
        ]).mapped('res_id')
        positive = (operator in ('=', 'in')) == bool(value)
        return [('id', 'in' if positive else 'not in', ids)]
