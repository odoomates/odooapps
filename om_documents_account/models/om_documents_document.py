from odoo import models
from odoo.exceptions import UserError

MOVE_TYPES = ('in_invoice', 'in_refund', 'out_invoice', 'out_refund')


class DocumentsDocument(models.Model):
    _inherit = 'om.documents.document'

    def _create_move(self, move_type, journal=None):
        """ :return: the invoice or bill of `move_type` made from the file of the document, read like an upload
                     to the journal (the e-invoices and, when a module reads them, the PDFs and scans) """
        self.ensure_one()
        if move_type not in MOVE_TYPES:
            raise UserError(self.env._('Unknown kind of invoice: %s', move_type))
        if not self.attachment_id:
            raise UserError(self.env._('%s has no file to make an invoice from.', self.name))
        if self.res_model == 'account.move' and self._get_record():
            raise UserError(self.env._('%(document)s already has the invoice %(move)s.', document=self.name,
                                       move=self.res_name))
        self.check_access('write')
        Move = self.env['account.move']
        Move.check_access('create')
        # the move takes a copy of the file: the document keeps its own
        copy = self.attachment_id.sudo().with_context(om_documents_no_sync=True).copy(
            {'res_model': False, 'res_id': False})
        Journal = self.env['account.journal'].with_context(default_move_type=move_type, om_documents_no_sync=True)
        if journal:
            Journal = Journal.with_context(default_journal_id=journal.id)
        moves = (journal or Journal)._create_document_from_attachment(copy.ids)
        move = moves[:1]
        values = {'res_model': move._name, 'res_id': move.id}
        if move.partner_id and not self.partner_id:
            values['partner_id'] = move.partner_id.commercial_partner_id.id
        self.write(values)
        self.message_post(body=self.env._('%(move)s created from the document.', move=move._get_html_link()),
                          subtype_xmlid='mail.mt_note')
        move.message_post(body=self.env._('Created from the document %s.', self._get_html_link()),
                          subtype_xmlid='mail.mt_note')
        return moves

    def _action_create_moves(self, move_type):
        moves = self.env['account.move']
        for document in self:
            moves |= document._create_move(move_type)
        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'name': self.env._('Created Invoices'),
            'context': {'default_move_type': move_type},
        }
        if len(moves) == 1:
            action.update(res_id=moves.id, view_mode='form', views=[(False, 'form')])
        else:
            action.update(domain=[('id', 'in', moves.ids)], view_mode='list,form',
                          views=[(False, 'list'), (False, 'form')])
        return action

    def action_create_vendor_bill(self):
        return self._action_create_moves('in_invoice')

    def action_create_vendor_refund(self):
        return self._action_create_moves('in_refund')

    def action_create_customer_invoice(self):
        return self._action_create_moves('out_invoice')

    def action_create_customer_refund(self):
        return self._action_create_moves('out_refund')
