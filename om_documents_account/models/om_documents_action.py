from odoo import fields, models


class DocumentsAction(models.Model):
    _inherit = 'om.documents.action'

    create_model = fields.Selection(selection_add=[
        ('in_invoice', 'Vendor Bill'),
        ('in_refund', 'Vendor Credit Note'),
        ('out_invoice', 'Customer Invoice'),
        ('out_refund', 'Customer Credit Note'),
    ], ondelete={
        'in_invoice': 'set default',
        'in_refund': 'set default',
        'out_invoice': 'set default',
        'out_refund': 'set default',
    })
    journal_id = fields.Many2one('account.journal', string='Journal', domain=[('type', 'in', ['sale', 'purchase'])],
                                 help='Leave empty for the first journal of the kind of invoice.')

    def _create_records_moves(self, documents):
        moves = self.env['account.move']
        for document in documents:
            moves |= document._create_move(self.create_model, journal=self.journal_id or None)
        return moves

    def _create_records_in_invoice(self, documents):
        return self._create_records_moves(documents)

    def _create_records_in_refund(self, documents):
        return self._create_records_moves(documents)

    def _create_records_out_invoice(self, documents):
        return self._create_records_moves(documents)

    def _create_records_out_refund(self, documents):
        return self._create_records_moves(documents)
