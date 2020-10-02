# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountInvoice(models.Model):
    _inherit = 'account.move'

    @api.model
    def _refund_cleanup_lines(self, lines):
        result = super(AccountInvoice, self)._refund_cleanup_lines(lines)
        for i, line in enumerate(lines):
            for name, field in line._fields.items():
                if name == 'asset_category_id':
                    result[i][2][name] = False
                    break
        return result

    def action_cancel(self):
        res = super(AccountInvoice, self).action_cancel()
        self.env['account.asset.asset'].sudo().search([('invoice_id', 'in', self.ids)]).write({'active': False})
        return res

    def action_post(self):
        result = super(AccountInvoice, self).action_post()
        for inv in self:
            context = dict(self.env.context)
            context.pop('default_type', None)
            for mv_line in inv.invoice_line_ids:
                mv_line.with_context(context).asset_create()
        return result


class AccountInvoiceLine(models.Model):
    _inherit = 'account.move.line'

    asset_category_id = fields.Many2one('account.asset.category', string='Asset Category')
    asset_start_date = fields.Date(string='Asset Start Date', compute='_get_asset_date', readonly=True, store=True)
    asset_end_date = fields.Date(string='Asset End Date', compute='_get_asset_date', readonly=True, store=True)
    asset_mrr = fields.Float(string='Monthly Recurring Revenue', compute='_get_asset_date', readonly=True,
                             digits="Account", store=True)

    @api.depends('asset_category_id', 'move_id.invoice_date')
    def _get_asset_date(self):
        for rec in self:
            rec.asset_mrr = 0
            rec.asset_start_date = False
            rec.asset_end_date = False
            cat = rec.asset_category_id
            if cat:
                if cat.method_number == 0 or cat.method_period == 0:
                    raise UserError(_('The number of depreciations or the period length of '
                                      'your asset category cannot be 0.'))
                months = cat.method_number * cat.method_period
                if rec.move_id.type in ['out_invoice', 'out_refund']:
                    rec.asset_mrr = rec.price_subtotal / months
                if rec.move_id.invoice_date:
                    start_date = rec.move_id.invoice_date.replace(day=1)
                    end_date = (start_date + relativedelta(months=months, days=-1))
                    rec.asset_start_date = start_date
                    rec.asset_end_date = end_date

    def asset_create(self):
        if self.asset_category_id:
            vals = {
                'name': self.name,
                'code': self.name or False,
                'category_id': self.asset_category_id.id,
                'value': self.price_subtotal,
                'partner_id': self.move_id.partner_id.id,
                'company_id': self.move_id.company_id.id,
                'currency_id': self.move_id.company_currency_id.id,
                'date': self.move_id.invoice_date,
                'invoice_id': self.move_id.id,
            }
            changed_vals = self.env['account.asset.asset'].onchange_category_id_values(vals['category_id'])
            vals.update(changed_vals['value'])
            asset = self.env['account.asset.asset'].create(vals)
            if self.asset_category_id.open_asset:
                asset.validate()
        return True

    @api.onchange('asset_category_id')
    def onchange_asset_category_id(self):
        if self.move_id.type == 'out_invoice' and self.asset_category_id:
            self.account_id = self.asset_category_id.account_asset_id.id
        elif self.move_id.type == 'in_invoice' and self.asset_category_id:
            self.account_id = self.asset_category_id.account_asset_id.id

    @api.onchange('uom_id')
    def _onchange_uom_id(self):
        result = super(AccountInvoiceLine, self)._onchange_uom_id()
        self.onchange_asset_category_id()
        return result

    @api.onchange('product_id')
    def _onchange_product_id(self):
        vals = super(AccountInvoiceLine, self)._onchange_product_id()
        if self.product_id:
            if self.move_id.type == 'out_invoice':
                self.asset_category_id = self.product_id.product_tmpl_id.deferred_revenue_category_id
            elif self.move_id.type == 'in_invoice':
                self.asset_category_id = self.product_id.product_tmpl_id.asset_category_id
        return vals

    def _set_additional_fields(self, invoice):
        if not self.asset_category_id:
            if invoice.type == 'out_invoice':
                self.asset_category_id = self.product_id.product_tmpl_id.deferred_revenue_category_id.id
            elif invoice.type == 'in_invoice':
                self.asset_category_id = self.product_id.product_tmpl_id.asset_category_id.id
            self.onchange_asset_category_id()
        super(AccountInvoiceLine, self)._set_additional_fields(invoice)

    def get_invoice_line_account(self, type, product, fpos, company):
        return product.asset_category_id.account_asset_id or super(AccountInvoiceLine, self).get_invoice_line_account(type, product, fpos, company)
