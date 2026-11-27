from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_documents_account_sync = fields.Boolean(
        string='Invoices in Documents', default=True,
        help='The files of the invoices and the bills are kept in the Accounting folder of Documents.')
    om_documents_account_folder_id = fields.Many2one(
        'om.documents.folder', string='Accounting Folder',
        default=lambda self: self.env.ref('om_documents_account.folder_accounting', raise_if_not_found=False))

    @api.model
    def _om_documents_account_init_folder(self):
        folder = self.env.ref('om_documents_account.folder_accounting', raise_if_not_found=False)
        if folder:
            self.search([('om_documents_account_folder_id', '=', False)]).om_documents_account_folder_id = folder


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_documents_account_sync = fields.Boolean(related='company_id.om_documents_account_sync', readonly=False)
    om_documents_account_folder_id = fields.Many2one(related='company_id.om_documents_account_folder_id',
                                                     readonly=False)
