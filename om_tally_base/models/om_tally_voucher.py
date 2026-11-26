from odoo import api, fields, models

from ..tools import ACCOUNTING_VOUCHER_TYPES


class OmTallyVoucher(models.Model):
    _name = 'om.tally.voucher'
    _description = 'Tally Voucher'
    _order = 'date, voucher_type_name, id'
    _rec_name = 'display_number'

    import_id = fields.Many2one('om.tally.import', string='Tally Import', required=True, ondelete='cascade',
                                index=True)
    company_id = fields.Many2one(related='import_id.company_id', store=True)
    currency_id = fields.Many2one(related='import_id.company_id.currency_id')
    guid = fields.Char(string='Tally GUID', index=True, readonly=True)
    alter_id = fields.Integer(string='Alter ID', readonly=True)
    master_id = fields.Integer(string='Master ID', readonly=True)
    date = fields.Date(required=True, index=True, readonly=True)
    effective_date = fields.Date(readonly=True)
    fiscal_year = fields.Char(string='Financial Year', compute='_compute_fiscal_year', store=True)
    voucher_type_name = fields.Char(string='Voucher Type Name', readonly=True)
    voucher_type_id = fields.Many2one('om.tally.voucher.type', string='Voucher Type', ondelete='set null',
                                      index=True)
    base_type = fields.Char(string='Base Voucher Type', compute='_compute_base_type', store=True,
                            help="The predefined type of Tally (Sales, Purchase, Receipt...).")
    number = fields.Char(string='Voucher Number', readonly=True)
    display_number = fields.Char(string='Voucher', compute='_compute_display_number', store=True)
    reference = fields.Char(string='Supplier Invoice No.', readonly=True)
    reference_date = fields.Date(readonly=True)
    party_name = fields.Char(string='Party Name', readonly=True)
    party_ledger_id = fields.Many2one('om.tally.ledger', string='Party', ondelete='set null', index=True)
    narration = fields.Text(readonly=True)
    is_cancelled = fields.Boolean(string='Cancelled', readonly=True)
    is_optional = fields.Boolean(string='Optional', readonly=True)
    is_postdated = fields.Boolean(string='Post-Dated', readonly=True)
    is_invoice = fields.Boolean(string='Invoice Mode', readonly=True)
    is_deleted = fields.Boolean(string='Deleted in Tally', readonly=True)
    is_changed = fields.Boolean(string='Changed in Tally', readonly=True,
                                help="Tally changed this voucher after it was imported: check the Odoo entry.")
    view = fields.Char(string='Tally View', readonly=True)
    is_accounting = fields.Boolean(string='Posts to the Books', compute='_compute_is_accounting', store=True,
                                   help="The voucher posts to the books: not cancelled, optional, post-dated, "
                                        "deleted, nor of a non-accounting type (orders, notes, stock journals).")
    amount = fields.Monetary(compute='_compute_amount', store=True, string='Amount')
    difference = fields.Monetary(compute='_compute_amount', store=True, string='Unbalanced',
                                 help="Debits minus credits: zero for a sound voucher.")
    line_ids = fields.One2many('om.tally.voucher.line', 'voucher_id', string='Ledger Entries')
    inventory_ids = fields.One2many('om.tally.voucher.inventory', 'voucher_id', string='Inventory Entries')
    state = fields.Selection([
        ('staged', 'To Import'),
        ('skipped', 'Skipped'),
        ('posted', 'Imported'),
        ('error', 'Error'),
    ], default='staged', required=True, index=True, readonly=True)
    error_message = fields.Text(readonly=True)

    @api.depends('date', 'import_id.starting_from')
    def _compute_fiscal_year(self):
        for voucher in self:
            if not voucher.date:
                voucher.fiscal_year = False
                continue
            month = voucher.import_id.starting_from.month if voucher.import_id.starting_from else 4
            start_year = voucher.date.year if voucher.date.month >= month else voucher.date.year - 1
            voucher.fiscal_year = str(start_year) if month == 1 else f'{start_year}-{str(start_year + 1)[-2:]}'

    @api.depends('voucher_type_id.base_type', 'voucher_type_name')
    def _compute_base_type(self):
        for voucher in self:
            voucher.base_type = voucher.voucher_type_id.base_type or voucher.voucher_type_name

    @api.depends('voucher_type_name', 'number', 'date')
    def _compute_display_number(self):
        for voucher in self:
            voucher.display_number = f"{voucher.voucher_type_name or ''} {voucher.number or ''}".strip() or \
                str(voucher.date or '')

    @api.depends('base_type', 'is_cancelled', 'is_optional', 'is_postdated', 'is_deleted')
    def _compute_is_accounting(self):
        for voucher in self:
            voucher.is_accounting = voucher.base_type in ACCOUNTING_VOUCHER_TYPES and not (
                voucher.is_cancelled or voucher.is_optional or voucher.is_postdated or voucher.is_deleted)

    @api.depends('line_ids.amount')
    def _compute_amount(self):
        for voucher in self:
            amounts = voucher.line_ids.mapped('amount')
            voucher.amount = sum(amount for amount in amounts if amount > 0)
            voucher.difference = voucher.currency_id.round(sum(amounts)) if voucher.currency_id else sum(amounts)


class OmTallyVoucherLine(models.Model):
    _name = 'om.tally.voucher.line'
    _description = 'Tally Ledger Entry'
    _order = 'voucher_id, sequence, id'

    voucher_id = fields.Many2one('om.tally.voucher', required=True, ondelete='cascade', index=True)
    import_id = fields.Many2one(related='voucher_id.import_id', store=True, index=True)
    date = fields.Date(related='voucher_id.date', store=True)
    currency_id = fields.Many2one(related='voucher_id.currency_id')
    sequence = fields.Integer(default=10)
    ledger_name = fields.Char(required=True, readonly=True)
    ledger_id = fields.Many2one('om.tally.ledger', string='Ledger', ondelete='set null', index=True)
    amount = fields.Monetary(readonly=True, help="Debit positive, credit negative.")
    debit = fields.Monetary(compute='_compute_debit_credit')
    credit = fields.Monetary(compute='_compute_debit_credit')
    is_deemed_positive = fields.Boolean(string='Debit Side', readonly=True)
    is_party = fields.Boolean(string='Party Ledger', readonly=True)
    from_inventory = fields.Boolean(string='From an Item Line', readonly=True,
                                    help="The accounting allocation of an inventory line (invoice mode).")
    instrument_number = fields.Char(string='Cheque/Instrument No.', readonly=True)
    instrument_date = fields.Date(readonly=True)
    bill_ids = fields.One2many('om.tally.voucher.bill', 'line_id', string='Bill Allocations')
    cost_ids = fields.One2many('om.tally.voucher.cost', 'line_id', string='Cost Centre Allocations')

    @api.depends('amount')
    def _compute_debit_credit(self):
        for line in self:
            line.debit = max(line.amount, 0.0)
            line.credit = max(-line.amount, 0.0)


class OmTallyVoucherBill(models.Model):
    _name = 'om.tally.voucher.bill'
    _description = 'Tally Bill Allocation'
    _order = 'line_id, id'

    line_id = fields.Many2one('om.tally.voucher.line', required=True, ondelete='cascade', index=True)
    voucher_id = fields.Many2one(related='line_id.voucher_id', store=True, index=True)
    import_id = fields.Many2one(related='line_id.import_id', store=True, index=True)
    ledger_id = fields.Many2one(related='line_id.ledger_id', store=True)
    currency_id = fields.Many2one(related='line_id.currency_id')
    name = fields.Char(string='Bill Reference')
    bill_type = fields.Selection([
        ('new', 'New Ref'), ('agst', 'Agst Ref'), ('advance', 'Advance'), ('on_account', 'On Account'),
    ], required=True, default='on_account')
    amount = fields.Monetary(help="Debit positive, credit negative.")
    credit_period = fields.Char()
    due_date = fields.Date()


class OmTallyVoucherCost(models.Model):
    _name = 'om.tally.voucher.cost'
    _description = 'Tally Cost Centre Allocation'
    _order = 'line_id, id'

    line_id = fields.Many2one('om.tally.voucher.line', required=True, ondelete='cascade', index=True)
    import_id = fields.Many2one(related='line_id.import_id', store=True, index=True)
    currency_id = fields.Many2one(related='line_id.currency_id')
    category_name = fields.Char(string='Cost Category Name')
    name = fields.Char(string='Cost Centre Name')
    cost_centre_id = fields.Many2one('om.tally.cost.centre', string='Cost Centre', ondelete='set null')
    amount = fields.Monetary()


class OmTallyVoucherInventory(models.Model):
    _name = 'om.tally.voucher.inventory'
    _description = 'Tally Inventory Entry'
    _order = 'voucher_id, id'

    voucher_id = fields.Many2one('om.tally.voucher', required=True, ondelete='cascade', index=True)
    import_id = fields.Many2one(related='voucher_id.import_id', store=True, index=True)
    currency_id = fields.Many2one(related='voucher_id.currency_id')
    item_name = fields.Char(string='Stock Item Name', readonly=True)
    item_id = fields.Many2one('om.tally.stock.item', string='Stock Item', ondelete='set null', index=True)
    quantity = fields.Float(readonly=True, digits=(16, 3))
    unit_name = fields.Char(string='Unit', readonly=True)
    rate = fields.Float(readonly=True, digits=(16, 4))
    discount = fields.Float(string='Discount (%)', readonly=True)
    amount = fields.Monetary(readonly=True)
    is_inward = fields.Boolean(string='Inward', readonly=True)
    godown_name = fields.Char(readonly=True)
    godown_id = fields.Many2one('om.tally.godown', string='Godown', ondelete='set null')
    batch_name = fields.Char(string='Batch', readonly=True)
    ledger_name = fields.Char(string='Accounting Ledger', readonly=True)
