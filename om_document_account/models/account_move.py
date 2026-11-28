from odoo import models
from odoo.fields import Command


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'om.documents.mixin']

    def _get_documents_folder(self):
        company = self.company_id or self.env.company
        if not company.om_documents_account_sync or self.move_type == 'entry':
            return self.env['om.documents.folder']
        return company.om_documents_account_folder_id

    def _get_documents_values(self):
        values = {}
        if self.partner_id:
            values['partner_id'] = self.partner_id.commercial_partner_id.id
        tag = self.env.ref('om_document_account.tag_%s' % self.move_type, raise_if_not_found=False)
        if tag:
            values['tag_ids'] = [Command.link(tag.id)]
        return values
