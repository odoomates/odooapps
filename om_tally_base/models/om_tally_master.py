from odoo import api, fields, models

from ..tools import PREDEFINED_GROUPS, PREDEFINED_VOUCHER_TYPES


class OmTallyStagingMixin(models.AbstractModel):
    """ A record read from Tally, kept as Tally sends it until the user imports it. """
    _name = 'om.tally.staging.mixin'
    _description = 'Tally Staging Record'
    _order = 'name'

    import_id = fields.Many2one('om.tally.import', string='Tally Import', required=True, ondelete='cascade',
                                index=True)
    company_id = fields.Many2one(related='import_id.company_id', store=True)
    name = fields.Char(required=True, index=True)
    guid = fields.Char(string='Tally GUID', index=True, readonly=True)
    alter_id = fields.Integer(string='Alter ID', readonly=True,
                              help="Tally raises it each time the record changes: the sync reads only what changed.")
    master_id = fields.Integer(string='Master ID', readonly=True)
    reserved_name = fields.Char(readonly=True, help="The name of a record Tally creates itself (predefined).")
    aliases = fields.Char(readonly=True)


class OmTallyRemoteCompany(models.Model):
    _name = 'om.tally.remote.company'
    _description = 'Company Open in Tally'
    _order = 'name'

    import_id = fields.Many2one('om.tally.import', required=True, ondelete='cascade', index=True)
    name = fields.Char(required=True)
    guid = fields.Char(string='Tally GUID')
    books_from = fields.Date(string='Books Beginning From')
    starting_from = fields.Date(string='Financial Year From')
    currency_symbol = fields.Char(string='Base Currency')

    def action_select(self):
        self.ensure_one()
        self.import_id.tally_company_name = self.name
        self.import_id.books_from = self.books_from or self.import_id.books_from
        self.import_id.starting_from = self.starting_from or self.import_id.starting_from
        return True


class OmTallyGroup(models.Model):
    _name = 'om.tally.group'
    _description = 'Tally Group'
    _inherit = 'om.tally.staging.mixin'
    _parent_name = 'parent_id'
    _parent_store = True

    parent_name = fields.Char(string='Parent Group Name', readonly=True)
    parent_id = fields.Many2one('om.tally.group', string='Parent Group', ondelete='set null', index=True)
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('om.tally.group', 'parent_id', string='Sub-Groups')
    ledger_ids = fields.One2many('om.tally.ledger', 'group_id', string='Ledgers')
    primary_group = fields.Char(compute='_compute_primary_group', store=True, recursive=True,
                                help="The predefined group of Tally this group belongs to.")
    nature = fields.Selection([
        ('asset', 'Assets'), ('liability', 'Liabilities'), ('income', 'Income'), ('expense', 'Expenses'),
    ], compute='_compute_primary_group', store=True, recursive=True)
    is_predefined = fields.Boolean(compute='_compute_primary_group', store=True, recursive=True)
    is_revenue = fields.Boolean(string='Revenue Group', readonly=True)
    affects_gross_profit = fields.Boolean(readonly=True)
    is_deemed_positive = fields.Boolean(string='Debit Nature', readonly=True)
    is_billwise = fields.Boolean(string='Bill-wise', readonly=True)
    is_subledger = fields.Boolean(string='Sub-Ledger', readonly=True)
    ledger_count = fields.Integer(compute='_compute_ledger_count')

    @api.depends('name', 'reserved_name', 'parent_id.primary_group', 'parent_id.nature')
    def _compute_primary_group(self):
        for group in self:
            predefined = group.reserved_name if group.reserved_name in PREDEFINED_GROUPS else (
                group.name if group.name in PREDEFINED_GROUPS and not group.parent_id else False)
            group.is_predefined = bool(predefined)
            if predefined:
                group.primary_group = predefined
                group.nature = PREDEFINED_GROUPS[predefined][0]
            elif group.parent_id:
                # a user group under a predefined sub-group (Sundry Debtors...) keeps that sub-group
                group.primary_group = group.parent_id.primary_group
                group.nature = group.parent_id.nature
            else:
                group.primary_group = False
                group.nature = (group.is_revenue and (group.is_deemed_positive and 'expense' or 'income')
                                or (group.is_deemed_positive and 'asset' or 'liability'))

    def _compute_ledger_count(self):
        Ledger = self.env['om.tally.ledger']
        for group in self:
            group.ledger_count = Ledger.search_count([('group_id', 'child_of', group.id)]) if group.id else 0


class OmTallyLedger(models.Model):
    _name = 'om.tally.ledger'
    _description = 'Tally Ledger'
    _inherit = 'om.tally.staging.mixin'

    parent_name = fields.Char(string='Group Name', readonly=True)
    group_id = fields.Many2one('om.tally.group', string='Group', ondelete='set null', index=True)
    primary_group = fields.Char(related='group_id.primary_group', store=True)
    nature = fields.Selection(related='group_id.nature', store=True)
    role = fields.Selection([
        ('receivable', 'Customer'),
        ('payable', 'Vendor'),
        ('bank', 'Bank'),
        ('cash', 'Cash'),
        ('tax', 'Tax'),
        ('stock', 'Stock'),
        ('pl', 'Profit & Loss'),
        ('account', 'Account'),
    ], compute='_compute_role', store=True,
        help="How the ledger comes into Odoo: a partner, a journal, a tax account or an account.")
    currency_id = fields.Many2one(related='import_id.company_id.currency_id')
    opening_balance = fields.Monetary(string='Opening Balance', readonly=True,
                                      help="Debit positive, credit negative.")
    opening_debit = fields.Monetary(compute='_compute_debit_credit', string='Opening Debit')
    opening_credit = fields.Monetary(compute='_compute_debit_credit', string='Opening Credit')
    currency_name = fields.Char(string='Tally Currency', readonly=True)
    is_billwise = fields.Boolean(string='Maintain Bill-wise', readonly=True)
    is_cost_centres_on = fields.Boolean(string='Cost Centres Applicable', readonly=True)
    credit_period = fields.Char(string='Default Credit Period', readonly=True)
    mailing_name = fields.Char(readonly=True)
    address = fields.Text(readonly=True)
    state_name = fields.Char(string='State', readonly=True)
    country_name = fields.Char(string='Country', readonly=True)
    pincode = fields.Char(string='PIN Code', readonly=True)
    email = fields.Char(readonly=True)
    phone = fields.Char(readonly=True)
    mobile = fields.Char(readonly=True)
    contact = fields.Char(string='Contact Person', readonly=True)
    website = fields.Char(readonly=True)
    gstin = fields.Char(string='GSTIN/UIN', readonly=True)
    gst_registration_type = fields.Char(string='GST Registration Type', readonly=True)
    vat_number = fields.Char(string='VAT/TRN Number', readonly=True)
    tax_number = fields.Char(string='Tax Number', compute='_compute_tax_number',
                             help="The GSTIN in India, the TRN or VAT number in the Gulf.")
    tally_country = fields.Selection(related='import_id.tally_country')
    pan = fields.Char(string='PAN/IT Number', readonly=True)
    tax_type = fields.Char(string='Type of Duty/Tax', readonly=True)
    gst_duty_head = fields.Char(string='GST Duty Head', readonly=True)
    tax_rate = fields.Float(string='Tax Rate (%)', readonly=True)
    bank_account_number = fields.Char(string='Bank Account Number', readonly=True)
    bank_ifsc = fields.Char(string='IFS Code', readonly=True)
    bank_name = fields.Char(string='Bank Name', readonly=True)
    bill_ids = fields.One2many('om.tally.ledger.bill', 'ledger_id', string='Opening Bills')
    bill_total = fields.Monetary(compute='_compute_bill_total', string='Total of the Opening Bills')
    voucher_line_count = fields.Integer(compute='_compute_voucher_line_count', string='Voucher Lines')

    @api.depends('primary_group', 'reserved_name', 'name', 'group_id')
    def _compute_role(self):
        roles = {
            'Sundry Debtors': 'receivable', 'Sundry Creditors': 'payable', 'Bank Accounts': 'bank',
            'Bank OD A/c': 'bank', 'Cash-in-Hand': 'cash', 'Duties & Taxes': 'tax', 'Stock-in-Hand': 'stock',
        }
        for ledger in self:
            if ledger.reserved_name == 'Profit & Loss A/c' or (not ledger.group_id and ledger.name == 'Profit & Loss A/c'):
                ledger.role = 'pl'
            else:
                ledger.role = roles.get(ledger.primary_group, 'account')

    @api.depends('gstin', 'vat_number')
    def _compute_tax_number(self):
        for ledger in self:
            ledger.tax_number = ledger.gstin or ledger.vat_number

    @api.depends('opening_balance')
    def _compute_debit_credit(self):
        for ledger in self:
            ledger.opening_debit = max(ledger.opening_balance, 0.0)
            ledger.opening_credit = max(-ledger.opening_balance, 0.0)

    @api.depends('bill_ids.amount')
    def _compute_bill_total(self):
        for ledger in self:
            ledger.bill_total = sum(ledger.bill_ids.mapped('amount'))

    def _compute_voucher_line_count(self):
        counts = dict(self.env['om.tally.voucher.line']._read_group(
            [('ledger_id', 'in', self.ids)], ['ledger_id'], ['__count']))
        for ledger in self:
            ledger.voucher_line_count = counts.get(ledger, 0)

    def action_open_voucher_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'om.tally.voucher.line',
            'view_mode': 'list,form',
            'domain': [('ledger_id', '=', self.id)],
        }


class OmTallyLedgerBill(models.Model):
    _name = 'om.tally.ledger.bill'
    _description = 'Tally Opening Bill'
    _order = 'bill_date, id'

    ledger_id = fields.Many2one('om.tally.ledger', required=True, ondelete='cascade', index=True)
    import_id = fields.Many2one(related='ledger_id.import_id', store=True, index=True)
    currency_id = fields.Many2one(related='ledger_id.currency_id')
    name = fields.Char(string='Bill Reference', required=True)
    bill_date = fields.Date()
    credit_period = fields.Char()
    due_date = fields.Date()
    amount = fields.Monetary(help="Debit positive, credit negative.")
    is_advance = fields.Boolean(string='Advance')


class OmTallyVoucherType(models.Model):
    _name = 'om.tally.voucher.type'
    _description = 'Tally Voucher Type'
    _inherit = 'om.tally.staging.mixin'

    parent_name = fields.Char(string='Type of Voucher', readonly=True)
    base_type = fields.Char(compute='_compute_base_type', store=True, recursive=True,
                            help="The predefined voucher type of Tally this type is based on.")
    parent_id = fields.Many2one('om.tally.voucher.type', string='Based On', ondelete='set null')
    numbering_method = fields.Char(readonly=True)
    is_active = fields.Boolean(string='Active in Tally', default=True, readonly=True)
    is_optional_default = fields.Boolean(string='Optional by Default', readonly=True)
    affects_stock = fields.Boolean(readonly=True)
    voucher_count = fields.Integer(compute='_compute_voucher_count')

    @api.depends('name', 'parent_name', 'parent_id.base_type')
    def _compute_base_type(self):
        for voucher_type in self:
            if voucher_type.name in PREDEFINED_VOUCHER_TYPES and voucher_type.parent_name in ('', voucher_type.name):
                voucher_type.base_type = voucher_type.name
            elif voucher_type.parent_id and voucher_type.parent_id != voucher_type:
                voucher_type.base_type = voucher_type.parent_id.base_type
            elif voucher_type.parent_name in PREDEFINED_VOUCHER_TYPES:
                voucher_type.base_type = voucher_type.parent_name
            else:
                voucher_type.base_type = voucher_type.name if voucher_type.name in PREDEFINED_VOUCHER_TYPES else False

    def _compute_voucher_count(self):
        counts = dict(self.env['om.tally.voucher']._read_group(
            [('voucher_type_id', 'in', self.ids)], ['voucher_type_id'], ['__count']))
        for voucher_type in self:
            voucher_type.voucher_count = counts.get(voucher_type, 0)


class OmTallyCostCategory(models.Model):
    _name = 'om.tally.cost.category'
    _description = 'Tally Cost Category'
    _inherit = 'om.tally.staging.mixin'

    allocate_revenue = fields.Boolean(string='Allocate Revenue Items', readonly=True)
    allocate_non_revenue = fields.Boolean(string='Allocate Non-Revenue Items', readonly=True)
    cost_centre_ids = fields.One2many('om.tally.cost.centre', 'category_id', string='Cost Centres')


class OmTallyCostCentre(models.Model):
    _name = 'om.tally.cost.centre'
    _description = 'Tally Cost Centre'
    _inherit = 'om.tally.staging.mixin'

    parent_name = fields.Char(string='Parent Cost Centre Name', readonly=True)
    parent_id = fields.Many2one('om.tally.cost.centre', string='Parent Cost Centre', ondelete='set null')
    category_name = fields.Char(string='Category Name', readonly=True)
    category_id = fields.Many2one('om.tally.cost.category', string='Cost Category', ondelete='set null')


class OmTallyCurrency(models.Model):
    _name = 'om.tally.currency'
    _description = 'Tally Currency'
    _inherit = 'om.tally.staging.mixin'

    formal_name = fields.Char(readonly=True)
    iso_code = fields.Char(string='ISO Code', readonly=True)
    decimal_places = fields.Integer(readonly=True)
    currency_id = fields.Many2one('res.currency', string='Odoo Currency', compute='_compute_currency_id',
                                  store=True, readonly=False)

    @api.depends('iso_code', 'formal_name', 'name')
    def _compute_currency_id(self):
        Currency = self.env['res.currency'].with_context(active_test=False)
        for currency in self:
            match = Currency
            if currency.iso_code:
                match = Currency.search([('name', '=ilike', currency.iso_code)], limit=1)
            if not match and currency.formal_name:
                match = Currency.search(['|', ('full_name', '=ilike', currency.formal_name),
                                         ('name', '=ilike', currency.formal_name)], limit=1)
            if not match and currency.name:
                match = Currency.search([('symbol', '=', currency.name)], limit=1)
            currency.currency_id = match


class OmTallyUnit(models.Model):
    _name = 'om.tally.unit'
    _description = 'Tally Unit'
    _inherit = 'om.tally.staging.mixin'

    formal_name = fields.Char(readonly=True)
    is_simple = fields.Boolean(string='Simple Unit', readonly=True, default=True)
    base_unit_name = fields.Char(string='First Unit', readonly=True)
    additional_unit_name = fields.Char(string='Second Unit', readonly=True)
    conversion = fields.Float(readonly=True, default=1.0)
    decimal_places = fields.Integer(readonly=True)
    uqc = fields.Char(string='Unit Quantity Code', readonly=True)


class OmTallyStockGroup(models.Model):
    _name = 'om.tally.stock.group'
    _description = 'Tally Stock Group'
    _inherit = 'om.tally.staging.mixin'

    parent_name = fields.Char(string='Parent Name', readonly=True)
    parent_id = fields.Many2one('om.tally.stock.group', string='Parent Stock Group', ondelete='set null')


class OmTallyStockCategory(models.Model):
    _name = 'om.tally.stock.category'
    _description = 'Tally Stock Category'
    _inherit = 'om.tally.staging.mixin'

    parent_name = fields.Char(string='Parent Name', readonly=True)
    parent_id = fields.Many2one('om.tally.stock.category', string='Parent Stock Category', ondelete='set null')


class OmTallyGodown(models.Model):
    _name = 'om.tally.godown'
    _description = 'Tally Godown'
    _inherit = 'om.tally.staging.mixin'

    parent_name = fields.Char(string='Parent Name', readonly=True)
    parent_id = fields.Many2one('om.tally.godown', string='Parent Godown', ondelete='set null')
    address = fields.Text(readonly=True)


class OmTallyStockItem(models.Model):
    _name = 'om.tally.stock.item'
    _description = 'Tally Stock Item'
    _inherit = 'om.tally.staging.mixin'

    parent_name = fields.Char(string='Stock Group Name', readonly=True)
    stock_group_id = fields.Many2one('om.tally.stock.group', string='Stock Group', ondelete='set null')
    category_name = fields.Char(string='Stock Category Name', readonly=True)
    stock_category_id = fields.Many2one('om.tally.stock.category', string='Stock Category', ondelete='set null')
    base_unit_name = fields.Char(string='Unit', readonly=True)
    unit_id = fields.Many2one('om.tally.unit', string='Tally Unit', ondelete='set null')
    additional_unit_name = fields.Char(string='Alternate Unit', readonly=True)
    part_number = fields.Char(readonly=True)
    description = fields.Text(readonly=True)
    hsn_code = fields.Char(string='HSN/SAC', readonly=True)
    gst_rate = fields.Float(string='GST Rate (%)', readonly=True)
    gst_applicable = fields.Char(string='GST Applicability', readonly=True)
    is_batchwise = fields.Boolean(string='Maintain in Batches', readonly=True)
    has_expiry = fields.Boolean(string='Expiry Dates', readonly=True)
    costing_method = fields.Char(readonly=True)
    currency_id = fields.Many2one(related='import_id.company_id.currency_id')
    opening_quantity = fields.Float(readonly=True, digits=(16, 3))
    opening_unit_name = fields.Char(readonly=True)
    opening_value = fields.Monetary(readonly=True)
    opening_rate = fields.Float(readonly=True, digits=(16, 4))
    opening_ids = fields.One2many('om.tally.stock.item.opening', 'item_id', string='Opening Stock')


class OmTallyStockItemOpening(models.Model):
    _name = 'om.tally.stock.item.opening'
    _description = 'Tally Opening Stock'
    _order = 'item_id, id'

    item_id = fields.Many2one('om.tally.stock.item', required=True, ondelete='cascade', index=True)
    import_id = fields.Many2one(related='item_id.import_id', store=True, index=True)
    currency_id = fields.Many2one(related='item_id.currency_id')
    godown_name = fields.Char(readonly=True)
    godown_id = fields.Many2one('om.tally.godown', string='Godown', ondelete='set null')
    batch_name = fields.Char(string='Batch', readonly=True)
    quantity = fields.Float(readonly=True, digits=(16, 3))
    unit_name = fields.Char(string='Unit', readonly=True)
    value = fields.Monetary(readonly=True)
    rate = fields.Float(readonly=True, digits=(16, 4))
    manufacturing_date = fields.Date(readonly=True)
    expiry_date = fields.Date(readonly=True)


class OmTallyPeriod(models.Model):
    """ A period of vouchers read, then imported, on its own (full history split by period). """
    _name = 'om.tally.period'
    _description = 'Tally Import Period'
    _order = 'date_from'

    import_id = fields.Many2one('om.tally.import', required=True, ondelete='cascade', index=True)
    date_from = fields.Date(string='From', required=True)
    date_to = fields.Date(string='To', required=True)
    state = fields.Selection([('read', 'Read'), ('imported', 'Imported')], default='read', required=True)
    voucher_count = fields.Integer(string='Vouchers Read', compute='_compute_counts')
    posted_count = fields.Integer(string='Vouchers Imported', compute='_compute_counts')

    def _compute_counts(self):
        Voucher = self.env['om.tally.voucher']
        for period in self:
            domain = [('import_id', '=', period.import_id.id), ('date', '>=', period.date_from),
                      ('date', '<=', period.date_to)]
            period.voucher_count = Voucher.search_count(domain)
            period.posted_count = Voucher.search_count(domain + [('state', '=', 'posted')])
