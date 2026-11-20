from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    asset_ids = fields.One2many(
        'account.asset.asset', 'invoice_id', string="Assets"
    )

    def button_draft(self):
        res = super(AccountMove, self).button_draft()
        for move in self:
            if any(asset_id.state != 'draft' for asset_id in move.asset_ids):
                raise ValidationError(_(
                    'You cannot reset to draft for an entry having a posted asset'))
            if move.asset_ids:
                move.asset_ids.sudo().write({'active': False})
                for asset in move.asset_ids:
                    asset.sudo().message_post(body=_("Vendor bill cancelled."))
        return res

    @api.model
    def _refund_cleanup_lines(self, lines):
        result = super(AccountMove, self)._refund_cleanup_lines(lines)
        for i, line in enumerate(lines):
            for name, field in line._fields.items():
                if name == 'asset_category_id':
                    result[i][2][name] = False
                    break
        return result

    def action_cancel(self):
        res = super(AccountMove, self).action_cancel()
        assets = self.env['account.asset.asset'].sudo().search(
            [('invoice_id', 'in', self.ids)])
        if assets:
            assets.sudo().write({'active': False})
            for asset in assets:
                asset.sudo().message_post(body=_("Vendor bill cancelled."))
        return res

    def action_post(self):
        result = super(AccountMove, self).action_post()
        # a vendor refund of an asset creates a negative asset, depreciated the other way round; the customer credit
        # notes keep the category of the reversed lines but do not create deferred revenues
        for inv in self.filtered(lambda m: m.move_type in ('in_invoice', 'out_invoice', 'in_refund')):
            context = dict(self.env.context)
            context.pop('default_type', None)
            lines = inv.invoice_line_ids
            if inv.move_type == 'in_refund':
                lines = lines.filtered(lambda line: line.asset_category_id.type == 'purchase')
            for mv_line in lines:
                mv_line.with_context(context).asset_create()
        return result


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    asset_category_id = fields.Many2one(
        'account.asset.category', string='Asset Category'
    )
    asset_start_date = fields.Date(
        string='Asset Start Date', compute='_get_asset_date',
        readonly=True, store=True
    )
    asset_end_date = fields.Date(
        string='Asset End Date', compute='_get_asset_date',
        readonly=True, store=True
    )
    asset_mrr = fields.Float(
        string='Monthly Recurring Revenue', compute='_get_asset_date',
        readonly=True, store=True
    )

    @api.model
    def default_get(self, fields):
        res = super(AccountMoveLine, self).default_get(fields)
        if self.env.context.get('create_bill') and not self.asset_category_id:
            if self.product_id and self.move_id.move_type == 'out_invoice' and \
                    self.product_id.product_tmpl_id.deferred_revenue_category_id:
                self.asset_category_id = self.product_id.product_tmpl_id.deferred_revenue_category_id.id
            elif self.product_id and self.product_id.product_tmpl_id.asset_category_id and \
                    self.move_id.move_type == 'in_invoice':
                self.asset_category_id = self.product_id.product_tmpl_id.asset_category_id.id
            self.onchange_asset_category_id()
        return res

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
                if rec.move_id.move_type in ['out_invoice', 'out_refund']:
                    price_subtotal = self.currency_id._convert(
                        self.price_subtotal,
                        self.company_currency_id,
                        self.company_id,
                        self.move_id.invoice_date or fields.Date.context_today(
                            self))

                    rec.asset_mrr = price_subtotal / months
                if rec.move_id.invoice_date:
                    start_date = rec.move_id.invoice_date.replace(day=1)
                    end_date = (start_date + relativedelta(months=months, days=-1))
                    rec.asset_start_date = start_date
                    rec.asset_end_date = end_date

    def _get_asset_capitalized_tax(self):
        """ :return: the taxes of the line booked on its own account, e.g. a tax that cannot be recovered and whose
        repartition has no account: they are part of the cost of the asset. In company currency, signed like the line.
        A tax line shared by several lines is split by their amounts. """
        self.ensure_one()
        move = self.move_id
        amount = 0.0
        tax_lines = move.line_ids.filtered(
            lambda line: line.tax_line_id and line.account_id == self.account_id and line.display_type == 'tax')
        for tax_line in tax_lines:
            bases = move.line_ids.filtered(
                lambda line: line.display_type == 'product' and line.account_id == self.account_id
                and tax_line.tax_line_id in line.tax_ids.flatten_taxes_hierarchy())
            total = sum(bases.mapped('balance'))
            if self in bases and not move.company_currency_id.is_zero(total):
                amount += tax_line.balance * self.balance / total
        return move.company_currency_id.round(amount)

    def asset_create(self):
        if self.asset_category_id:
            move = self.move_id
            category = self.asset_category_id
            if category.type == 'purchase':
                # the amount booked on the asset account, with the taxes booked on it; a vendor refund creates a
                # negative asset
                sign = -1 if move.move_type == 'in_refund' else 1
                price_subtotal = sign * move.company_currency_id.round(
                    abs(self.balance + self._get_asset_capitalized_tax()))
            else:
                price_subtotal = self.currency_id._convert(
                    self.price_subtotal,
                    self.company_currency_id,
                    self.company_id,
                    move.invoice_date or fields.Date.context_today(
                        self))
            vals = {
                'name': self.name,
                # the first line of the label: the product, without its description
                'code': (self.name or '').split('\n')[0].strip() or False,
                'category_id': self.asset_category_id.id,
                'value': price_subtotal,
                'partner_id': self.move_id.partner_id.id,
                'company_id': self.move_id.company_id.id,
                'currency_id': self.move_id.company_currency_id.id,
                'date': self.move_id.invoice_date or self.move_id.date,
                'invoice_id': self.move_id.id,
                'original_move_line_ids': [Command.set(self.ids)],
            }
            if move.move_type == 'in_refund':
                refunded = move.reversed_entry_id.asset_ids.filtered(
                    lambda asset: asset.category_id == category and asset.value > 0).sorted('id')
                vals.update({
                    'name': _('Refund: %s', vals['name'] or category.name),
                    'refunded_asset_id': refunded[:1].id,
                })
            changed_vals = self.env['account.asset.asset'].onchange_category_id_values(vals['category_id'])
            vals.update(changed_vals['value'])
            vals['salvage_value'] = category._get_salvage_value(price_subtotal)
            asset = self.env['account.asset.asset'].create(vals)
            if self.asset_category_id.open_asset:
                if asset.date_first_depreciation == 'manual':
                    asset.first_depreciation_manual_date = asset.date
                asset.validate()
        return True

    @api.onchange('asset_category_id', 'product_uom_id')
    def onchange_asset_category_id(self):
        if self.move_id.move_type == 'out_invoice' and self.asset_category_id:
            self.account_id = self.asset_category_id.account_asset_id.id
        elif self.move_id.move_type in ('in_invoice', 'in_refund') and self.asset_category_id:
            self.account_id = self.asset_category_id.account_asset_id.id

    @api.onchange('product_id')
    def _inverse_product_id(self):
        res = super(AccountMoveLine, self)._inverse_product_id()
        for rec in self:
            if rec.product_id:
                if rec.move_id.move_type == 'out_invoice':
                    rec.asset_category_id = rec.product_id.product_tmpl_id.deferred_revenue_category_id.id
                elif rec.move_id.move_type in ('in_invoice', 'in_refund'):
                    rec.asset_category_id = rec.product_id.product_tmpl_id.asset_category_id.id

    def get_invoice_line_account(self, type, product, fpos, company):
        return product.asset_category_id.account_asset_id or super(AccountMoveLine, self).get_invoice_line_account(type, product, fpos, company)
