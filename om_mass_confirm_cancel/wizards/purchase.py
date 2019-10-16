# -*- coding: utf-8 -*-

import logging
from odoo import models

_logger = logging.getLogger(__name__)


class PurchaseOrderConfirm(models.TransientModel):
    _name = 'purchase.order.confirm'
    _description = "Wizard - Purchase Order Confirm/Cancel"

    def purchase_confirm(self):
        """filter the records of the state 'draft' and 'sent',
        and will confirm this and others will be skipped"""
        quotations = self._context.get('active_ids')
        quotations_ids = self.env['purchase.order'].browse(quotations).\
            filtered(lambda x: x.state == 'draft' or x.state == "sent")
        for quotation in quotations_ids:
            quotation.button_confirm()

    def purchase_cancel(self):
        quotations = self._context.get('active_ids')
        quotations_ids = self.env['purchase.order'].browse(quotations)
        for quotation in quotations_ids:
            try:
                quotation.button_cancel()
            except:
                pass







