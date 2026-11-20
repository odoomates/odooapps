from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.http import request as http_request

EVENTS = [
    ('sent', 'Sent'),
    ('invited', 'Asked to Sign'),
    ('reminded', 'Reminded'),
    ('opened', 'Opened'),
    ('code_sent', 'Email Code Sent'),
    ('code_failed', 'Wrong Email Code'),
    ('code_verified', 'Email Verified'),
    ('signed', 'Signed'),
    ('declined', 'Declined'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
    ('expired', 'Expired'),
]


class SignLog(models.Model):
    """ What happened to a request, when, by whom and from where: the evidence of the signatures. Kept as written,
    never changed. """
    _name = 'sign.log'
    _description = 'Signature Evidence'
    _order = 'date, id'

    request_id = fields.Many2one('sign.request', required=True, ondelete='cascade', index=True, readonly=True)
    signer_id = fields.Many2one('sign.request.signer', ondelete='set null', readonly=True)
    company_id = fields.Many2one(related='request_id.company_id', store=True, index=True)
    event = fields.Selection(EVENTS, required=True, readonly=True)
    date = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True)
    partner_id = fields.Many2one('res.partner', string='By', readonly=True)
    user_id = fields.Many2one('res.users', readonly=True)
    ip = fields.Char(string='IP Address', readonly=True)
    user_agent = fields.Char(string='Browser', readonly=True)
    document_hash = fields.Char(string='Fingerprint', readonly=True)
    note = fields.Text(readonly=True)

    @api.model
    def _log(self, request, event, signer=None, document_hash=None, note=None):
        values = {
            'request_id': request.id,
            'signer_id': signer.id if signer else False,
            'event': event,
            'partner_id': (signer.partner_id if signer else self.env.user.partner_id).id,
            'user_id': self.env.user.id if not self.env.user._is_public() else False,
            'document_hash': document_hash,
            'note': note,
        }
        if http_request:
            values.update(ip=http_request.httprequest.remote_addr,
                          user_agent=(http_request.httprequest.headers.get('User-Agent') or '')[:256])
        return self.sudo().create(values)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise UserError(self.env._('The evidence of a signature is written as it happens, not by hand.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise UserError(self.env._('The evidence of a signature is kept as it was written.'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_evidence(self):
        raise UserError(self.env._('The evidence of a signature is kept as it was written.'))
