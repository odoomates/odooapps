# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def _get_invoice_in_payment_state(self):
        return 'in_payment'
