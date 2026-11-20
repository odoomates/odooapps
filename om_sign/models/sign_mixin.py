from odoo import fields, models


class SignMixin(models.AbstractModel):
    """ For the models whose records get documents signed, e.g. an offer letter signed by the candidate: a
    Signatures smart button, a button to send a PDF for signature, and hooks telling the record how it ends. """
    _name = 'sign.mixin'
    _description = 'Signature Requests Mixin'

    sign_request_count = fields.Integer(compute='_compute_sign_request_count', string='Signatures')

    def _sign_request_domain(self):
        return [('res_model', '=', self._name), ('res_id', 'in', self.ids)]

    def _compute_sign_request_count(self):
        counts = dict(self.env['sign.request']._read_group(
            self._sign_request_domain(), ['res_id'], ['__count']))
        for record in self:
            record.sign_request_count = counts.get(record.id, 0)

    def action_open_sign_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Signatures'),
            'res_model': 'sign.request',
            'view_mode': 'list,form',
            'domain': [('res_model', '=', self._name), ('res_id', '=', self.id)],
            'context': {'create': False},
        }

    def action_request_signature(self):
        """ A draft request to sign a PDF about the record, its signers suggested by the record. """
        self.ensure_one()
        request = self.env['sign.request']._create_for_record(self)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sign.request',
            'res_id': request.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def _sign_default_signers(self):
        """ :return: the signers to suggest when a PDF about the record is sent for signature, as a list of
                     (sequence, role, partner) """
        return []

    def _on_sign_completed(self, request):
        """ Hook: everyone signed `request`, its signed PDF is attached. """

    def _on_sign_declined(self, request):
        """ Hook: a signer declined `request`. """

    def _on_sign_cancelled(self, request):
        """ Hook: `request` was cancelled, or expired before everyone signed. """
