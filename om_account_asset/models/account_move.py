from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    asset_ids = fields.One2many(
        'account.asset.asset', 'invoice_id', string="Assets"
    )

    def button_draft(self):
        for move in self:
            closed_assets = move.asset_ids.filtered(lambda a: a.state == 'close')
            if closed_assets:
                raise ValidationError(_(
                    'You cannot reset to draft an entry whose assets are closed, sold or disposed: %s',
                    ', '.join(closed_assets.mapped('name'))))
            # the assets are created again when the entry is posted again
            running_assets = move.asset_ids.filtered(lambda a: a.state in ('open', 'paused'))
            for asset in running_assets:
                asset.sudo().set_to_cancelled()
                asset.sudo().message_post(body=_("Vendor bill reset to draft."))
            move.asset_ids.filtered(lambda a: a.state == 'draft').sudo().unlink()
        return super().button_draft()

    def action_cancel(self):
        res = super().action_cancel()
        assets = self.env['account.asset.asset'].sudo().search(
            [('invoice_id', 'in', self.ids)])
        if assets:
            assets.sudo().write({'active': False})
            for asset in assets:
                asset.sudo().message_post(body=_("Vendor bill cancelled."))
        return res

    def action_post(self):
        for bill in self.filtered(lambda m: m.move_type == 'in_invoice'):
            bill.invoice_line_ids.filtered(lambda line: not line.asset_category_id)._set_bill_asset_category()
        result = super().action_post()
        context = dict(self.env.context)
        context.pop('default_type', None)
        # credit notes keep the category of the reversed lines but do not create assets
        for inv in self.filtered(lambda m: m.move_type in ('in_invoice', 'out_invoice')):
            for mv_line in inv.invoice_line_ids:
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
                    price_subtotal = rec.currency_id._convert(
                        rec.price_subtotal,
                        rec.company_currency_id,
                        rec.company_id,
                        rec.move_id.invoice_date or fields.Date.context_today(rec))

                    rec.asset_mrr = price_subtotal / months
                if rec.move_id.invoice_date:
                    start_date = rec.move_id.invoice_date.replace(day=1)
                    end_date = (start_date + relativedelta(months=months, days=-1))
                    rec.asset_start_date = start_date
                    rec.asset_end_date = end_date

    def _set_bill_asset_category(self):
        """ Give the vendor bill lines booked on the asset account of a category creating its assets
        from bills the category of that account. """
        Category = self.env['account.asset.category']
        for line in self:
            if line.display_type == 'product' and line.account_id:
                category = Category._get_bill_categories(line.account_id, line.company_id)
                if len(category) == 1:
                    line.asset_category_id = category

    def _prepare_asset_vals(self):
        """ :return: list of values of the assets created by the line, one per unit when the category says so """
        self.ensure_one()
        move = self.move_id
        category = self.asset_category_id
        date = move.invoice_date or move.date
        currency = move.company_currency_id
        price_subtotal = currency.round(self.currency_id._convert(
            self.price_subtotal, currency, self.company_id, move.invoice_date or fields.Date.context_today(self)))
        base_vals = {
            'name': self.name or self.product_id.display_name or category.name,
            'code': self.name or False,
            'category_id': category.id,
            'value': price_subtotal,
            'partner_id': move.partner_id.id,
            'company_id': move.company_id.id,
            'currency_id': currency.id,
            'date': date,
            'invoice_id': move.id,
        }
        base_vals.update(self.env['account.asset.asset'].onchange_category_id_values(category.id)['value'])
        units = self.quantity
        if category.type != 'purchase' or not category.asset_per_unit or units <= 1 or units != int(units):
            return [base_vals]
        units = int(units)
        unit_value = currency.round(price_subtotal / units)
        vals_list = []
        for index in range(units):
            # the last asset takes the rounding difference
            value = unit_value if index < units - 1 else currency.round(price_subtotal - unit_value * (units - 1))
            vals_list.append({
                **base_vals,
                'name': _('%(name)s (%(index)s/%(count)s)', name=base_vals['name'], index=index + 1, count=units),
                'value': value,
            })
        return vals_list

    def asset_create(self):
        for line in self.filtered('asset_category_id'):
            # the users posting bills cannot confirm assets
            assets = self.env['account.asset.asset'].sudo().create(line._prepare_asset_vals())
            if line.asset_category_id.open_asset:
                for asset in assets:
                    if asset.date_first_depreciation == 'manual':
                        asset.first_depreciation_manual_date = asset.date
                assets.validate()
        return True

    @api.onchange('account_id')
    def _onchange_account_asset_category(self):
        for line in self:
            if line.move_id.move_type == 'in_invoice' and not line.asset_category_id:
                line._set_bill_asset_category()

    @api.onchange('asset_category_id', 'product_uom_id')
    def onchange_asset_category_id(self):
        if self.move_id.move_type == 'out_invoice' and self.asset_category_id:
            self.account_id = self.asset_category_id.account_asset_id.id
        elif self.move_id.move_type == 'in_invoice' and self.asset_category_id:
            self.account_id = self.asset_category_id.account_asset_id.id

    @api.onchange('product_id')
    def _inverse_product_id(self):
        res = super()._inverse_product_id()
        for rec in self:
            if rec.product_id:
                if rec.move_id.move_type == 'out_invoice':
                    rec.asset_category_id = rec.product_id.product_tmpl_id.deferred_revenue_category_id.id
                elif rec.move_id.move_type == 'in_invoice':
                    rec.asset_category_id = rec.product_id.product_tmpl_id.asset_category_id.id
