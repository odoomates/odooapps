# -*- coding: utf-8 -*-

import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


class AccountInvoiceCancel(models.TransientModel):
    _name = 'account.invoice.cancel'
    _description = "Wizard - Account Invoice Cancel"

    @api.multi
    def invoice_cancel(self):
        invoices = self._context.get('active_ids')
        invoices_ids = self.env['account.invoice'].browse(invoices).\
            filtered(lambda x: x.state != 'cancel')
        for invoice in invoices_ids:
            invoice.action_invoice_cancel()





