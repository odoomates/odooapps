from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError


class AssetCreateFromLines(models.TransientModel):
    """ One asset from journal items, e.g. the bill lines of the parts of a machine, or items booked on the asset
    account by a journal entry. """
    _name = 'asset.create.from.lines'
    _description = 'Create an Asset from Journal Items'

    line_ids = fields.Many2many('account.move.line', string='Journal Items', required=True)
    company_id = fields.Many2one('res.company', compute='_compute_from_lines')
    currency_id = fields.Many2one('res.currency', compute='_compute_from_lines')
    value = fields.Monetary(string='Gross Value', compute='_compute_from_lines')
    category_id = fields.Many2one(
        'account.asset.category', string='Category', required=True,
        compute='_compute_defaults', store=True, readonly=False, precompute=True,
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]")
    name = fields.Char(string='Asset Name', required=True, compute='_compute_defaults', store=True, readonly=False,
                       precompute=True)
    date = fields.Date(string='Date', required=True, compute='_compute_defaults', store=True, readonly=False,
                       precompute=True)
    confirm = fields.Boolean(string='Confirm the Asset', default=True)

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if 'line_ids' in fields and not res.get('line_ids') \
                and self.env.context.get('active_model') == 'account.move.line':
            res['line_ids'] = [Command.set(self.env.context.get('active_ids') or [])]
        return res

    @api.depends('line_ids')
    def _compute_from_lines(self):
        for wizard in self:
            lines = wizard.line_ids
            company = lines.company_id[:1] or self.env.company
            wizard.company_id = company
            wizard.currency_id = company.currency_id
            wizard.value = company.currency_id.round(sum(lines.mapped('balance')))

    @api.depends('line_ids')
    def _compute_defaults(self):
        Category = self.env['account.asset.category']
        for wizard in self:
            lines = wizard.line_ids
            company = lines.company_id[:1] or self.env.company
            category = lines.asset_category_id.filtered(lambda c: c.type == 'purchase')[:1] \
                or Category.search([('account_asset_id', 'in', lines.account_id.ids), ('type', '=', 'purchase'),
                                    ('company_id', '=', company.id)], limit=1)
            wizard.category_id = category
            first = lines.sorted(lambda line: (line.date, line.id))[:1]
            wizard.name = first.name or first.product_id.display_name or category.name or _('Asset')
            wizard.date = first.move_id.invoice_date or first.date

    def _check_lines(self):
        lines = self.line_ids
        if not lines:
            raise UserError(_('Select the journal items of the asset.'))
        if len(lines.company_id) > 1:
            raise UserError(_('The journal items must belong to one company.'))
        if lines.filtered(lambda line: line.parent_state != 'posted'):
            raise UserError(_('The journal items must be posted.'))
        used = self.env['account.asset.asset'].search([('original_move_line_ids', 'in', lines.ids)])
        if used:
            raise UserError(_('Some journal items already have an asset: %s', ', '.join(used.mapped('name'))))
        if self.company_id.currency_id.is_zero(self.value):
            raise UserError(_('The journal items add up to zero.'))

    def action_create(self):
        self.ensure_one()
        self._check_lines()
        lines = self.line_ids
        Asset = self.env['account.asset.asset']
        partners = lines.partner_id.commercial_partner_id
        vals = {
            'name': self.name,
            'category_id': self.category_id.id,
            'value': self.value,
            'date': self.date,
            'company_id': self.company_id.id,
            'currency_id': self.company_id.currency_id.id,
            'partner_id': partners.id if len(partners) == 1 else False,
            'invoice_id': lines.move_id.id if len(lines.move_id) == 1 else False,
            'original_move_line_ids': [Command.set(lines.ids)],
            **Asset.onchange_category_id_values(self.category_id.id)['value'],
            'salvage_value': self.category_id._get_salvage_value(self.value),
        }
        asset = Asset.create(vals)
        if self.confirm:
            if asset.date_first_depreciation == 'manual' and not asset.first_depreciation_manual_date:
                asset.first_depreciation_manual_date = asset.date
            asset.validate()
        return asset._open_assets_action(asset.name)
