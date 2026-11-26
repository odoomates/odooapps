from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class OmInterCompanyRule(models.Model):
    """What happens between two companies of the group: which documents of one
    company are created in the other, and how they are filled in there.

    The rule is read from the company that issues the document (``company_id``)
    to the one that receives it (``target_company_id``); a rule going both ways
    also applies from the target to the company. Settings that depend on the
    company receiving the document (its journals, the mappings) exist for both
    sides."""
    _name = 'om.inter.company.rule'
    _description = 'Inter-Company Rule'
    _order = 'sequence, id'

    name = fields.Char(compute='_compute_name', store=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string="Company", required=True, default=lambda self: self.env.company,
        help="The company issuing the documents.")
    target_company_id = fields.Many2one(
        'res.company', string="Other Company", required=True,
        help="The company receiving the documents: its partner is the customer or vendor in the company.")
    direction = fields.Selection(
        [('one_way', "One way"), ('both', "Both ways")], string="Direction", required=True, default='both',
        help="One way: only the documents of the company to the other company are created there. "
             "Both ways: the documents of the other company to the company are created in the company as well.")

    # invoices and bills
    mirror_invoices = fields.Boolean(
        string="Customer Invoices to Vendor Bills", default=True,
        help="A posted customer invoice or credit note to the other company becomes its vendor bill or refund.")
    mirror_bills = fields.Boolean(
        string="Vendor Bills to Customer Invoices",
        help="A posted vendor bill or refund from the other company becomes its customer invoice or credit note. "
             "Use it when the buying company enters the bill first.")
    target_state = fields.Selection(
        [('draft', "Draft"), ('posted', "Posted")], string="Create As", required=True, default='draft',
        help="Draft: the receiving company checks and posts the document. Posted: it is posted at once.")
    user_id = fields.Many2one(
        'res.users', string="Created By", domain=[('share', '=', False)],
        help="The user the documents are created as in the receiving company. The person posting the invoice "
             "needs no access to that company. Empty: OdooBot.")
    copy_pdf = fields.Boolean(
        string="Attach the Invoice PDF", default=True,
        help="The PDF of the issued invoice is attached to the document created, as the original document.")
    on_source_change = fields.Selection(
        [('warn', "Warn"), ('follow', "Follow")], string="When the Source Changes", required=True, default='warn',
        help="When the issued document is reset to draft or cancelled. Warn: a warning is shown on the document "
             "created from it. Follow: the document created from it is reset or cancelled too, unless it is paid.")

    # mapping
    account_mode = fields.Selection(
        [('product', "From products and journal"), ('code', "Same account code")], string="Accounts",
        required=True, default='product',
        help="From products and journal: the accounts the receiving company uses for the products (its expense "
             "account on a bill). Same account code: the account with the code of the issued line. The account "
             "mapping below comes first in both cases.")
    tax_mode = fields.Selection(
        [('match', "Matching rate"), ('product', "From products")], string="Taxes", required=True,
        default='match',
        help="Matching rate: the purchase tax of the receiving company with the rate of the sales tax (or the "
             "reverse). From products: the taxes of the product in the receiving company. The fiscal position "
             "of the partner then applies. A tax of the tax mapping is used as mapped.")
    analytic_mode = fields.Selection(
        [('keep', "Copy"), ('none', "Leave to the receiving company")], string="Analytic", required=True,
        default='none',
        help="Copy: the analytic distribution of the lines is copied when its analytic accounts are shared "
             "with the receiving company. Leave to the receiving company: its analytic distribution models apply.")
    currency_mode = fields.Selection(
        [('source', "Currency of the document"), ('company', "Currency of the receiving company")],
        string="Currency", required=True, default='source',
        help="Currency of the document: the bill is in the currency of the invoice, as owed. Currency of the "
             "receiving company: the prices are converted at the rate of the invoice date.")

    # journals, per receiving company
    target_sale_journal_id = fields.Many2one(
        'account.journal', string="Sales Journal",
        domain="[('type', '=', 'sale'), ('company_id', '=', target_company_id)]",
        help="The journal of the customer invoices created in the other company. Empty: its first sales journal.")
    target_purchase_journal_id = fields.Many2one(
        'account.journal', string="Purchase Journal",
        domain="[('type', '=', 'purchase'), ('company_id', '=', target_company_id)]",
        help="The journal of the vendor bills created in the other company. Empty: its first purchase journal.")
    source_sale_journal_id = fields.Many2one(
        'account.journal', string="Sales Journal of the Company",
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]",
        help="The journal of the customer invoices created in the company. Empty: its first sales journal.")
    source_purchase_journal_id = fields.Many2one(
        'account.journal', string="Purchase Journal of the Company",
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]",
        help="The journal of the vendor bills created in the company. Empty: its first purchase journal.")

    account_map_ids = fields.One2many('om.inter.company.account.map', 'rule_id', string="Account Mapping")
    tax_map_ids = fields.One2many('om.inter.company.tax.map', 'rule_id', string="Tax Mapping")
    product_map_ids = fields.One2many('om.inter.company.product.map', 'rule_id', string="Product Mapping")
    note = fields.Html(string="Notes")

    _om_companies_differ = models.Constraint(
        'CHECK(company_id != target_company_id)', "A rule is between two different companies.")

    @api.depends('company_id', 'target_company_id', 'direction')
    def _compute_name(self):
        for rule in self:
            arrow = '⇄' if rule.direction == 'both' else '→'
            rule.name = '%s %s %s' % (rule.company_id.name or '', arrow, rule.target_company_id.name or '')

    @api.constrains('company_id', 'target_company_id', 'direction', 'active')
    def _check_om_pair(self):
        for rule in self.filtered('active'):
            pair = Domain('company_id', '=', rule.company_id.id) & Domain('target_company_id', '=', rule.target_company_id.id)
            reverse = Domain('company_id', '=', rule.target_company_id.id) & Domain(
                'target_company_id', '=', rule.company_id.id)
            others = self.search(Domain('id', '!=', rule.id) & (pair | reverse))
            if others:
                raise ValidationError(self.env._(
                    "There is already a rule between %(company)s and %(other)s: %(rule)s.",
                    company=rule.company_id.name, other=rule.target_company_id.name, rule=others[0].name))

    @api.constrains('user_id', 'company_id', 'target_company_id', 'direction')
    def _check_om_user(self):
        for rule in self.filtered('user_id'):
            needed = rule.target_company_id | (rule.company_id if rule.direction == 'both' else self.env['res.company'])
            missing = needed - rule.user_id.company_ids
            if missing:
                raise ValidationError(self.env._(
                    "The user %(user)s creates the documents of this rule but has no access to %(companies)s.",
                    user=rule.user_id.name, companies=', '.join(missing.mapped('name'))))

    # ------------------------------------------------------------------
    # Finding the rule
    # ------------------------------------------------------------------

    @api.model
    def _om_ic_get(self, company, other):
        """The active rule from ``company`` to ``other``, or an empty recordset."""
        if not company or not other or company == other:
            return self.browse()
        domain = (Domain('company_id', '=', company.id) & Domain('target_company_id', '=', other.id)) | (
            Domain('company_id', '=', other.id) & Domain('target_company_id', '=', company.id)
            & Domain('direction', '=', 'both'))
        return self.sudo().search(domain, limit=1)

    def _om_ic_forward(self, target):
        """Whether documents go from the company of the rule to ``target`` (the other company)."""
        self.ensure_one()
        return target == self.target_company_id

    def _om_ic_journal(self, target, journal_type):
        """The journal of ``journal_type`` (sale, purchase) the documents are created in, in ``target``."""
        self.ensure_one()
        if self._om_ic_forward(target):
            journal = self.target_sale_journal_id if journal_type == 'sale' else self.target_purchase_journal_id
        else:
            journal = self.source_sale_journal_id if journal_type == 'sale' else self.source_purchase_journal_id
        if journal:
            return journal
        return self.env['account.journal'].sudo().search(
            Domain('type', '=', journal_type) & Domain('company_id', '=', target.id), limit=1)

    def _om_ic_env(self, company):
        """An environment to create documents in ``company``: as the user of the rule (OdooBot by default),
        in that company only, without the defaults of the screen the document came from."""
        self.ensure_one()
        user = self.user_id or self.env['res.users'].browse(SUPERUSER_ID)
        context = {key: value for key, value in self.env.context.items()
                   if key in ('lang', 'tz') or key.startswith('om_ic_')}
        context.update(allowed_company_ids=[company.id], om_ic_no_mirror=True)
        return self.env(user=user.id, su=False, context=context)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def _om_ic_lookup(self, lines, field, record, target):
        """The record ``record`` maps to in ``target``, from the mapping ``lines`` on ``field``
        (account, tax, product), or an empty recordset."""
        if not record:
            return record
        mine, theirs = ('company_%s' % field, 'target_%s' % field)
        if not self._om_ic_forward(target):
            mine, theirs = theirs, mine
        line = lines.filtered(lambda map_line: map_line[mine] == record)[:1]
        return line[theirs] if line else record.browse()

    def _om_ic_map_product(self, product, target):
        self.ensure_one()
        if not product:
            return product
        mapped = self._om_ic_lookup(self.product_map_ids, 'product_id', product, target)
        if mapped:
            return mapped
        if not product.company_id or product.company_id == target or product.company_id in target.parent_ids:
            return product
        return product.browse()

    def _om_ic_map_account(self, account, target, source_company):
        """The account of ``target`` for ``account`` of ``source_company``, or an empty recordset to let
        the receiving company choose it from the product and the journal."""
        self.ensure_one()
        mapped = self._om_ic_lookup(self.account_map_ids, 'account_id', account, target)
        if mapped or self.account_mode != 'code' or not account:
            return mapped
        if target in account.company_ids or target.root_id in account.company_ids:
            return account
        code = account.with_company(source_company).code
        Account = self.env['account.account'].sudo().with_company(target)
        return Account.search(Domain(Account._check_company_domain(target)) & Domain('code', '=', code), limit=1)

    def _om_ic_map_taxes(self, taxes, target, tax_use, product, fiscal_position):
        """The taxes of ``target`` of ``tax_use`` (sale, purchase) for ``taxes``: a mapped tax as mapped, else
        the tax found (same rate, or of the product) as the fiscal position of the partner maps it."""
        self.ensure_one()
        Tax = self.env['account.tax'].sudo().with_company(target)
        company_domain = Domain(Tax._check_company_domain(target))

        def fiscal(found):
            return fiscal_position.map_tax(found) if fiscal_position else found

        result = Tax
        unmapped = Tax
        for tax in taxes:
            mapped = self._om_ic_lookup(self.tax_map_ids, 'tax_id', tax, target)
            if mapped:
                result |= mapped
            else:
                unmapped |= tax
        if not unmapped:
            return result
        if self.tax_mode == 'product' and product:
            field = 'taxes_id' if tax_use == 'sale' else 'supplier_taxes_id'
            return result | fiscal(product.sudo().with_company(target)[field].filtered_domain(company_domain))
        for tax in unmapped:
            candidates = Tax.search(company_domain & Domain([
                ('type_tax_use', '=', tax_use), ('amount_type', '=', tax.amount_type), ('amount', '=', tax.amount)]))
            if tax.amount:
                # a price including the tax read as excluding it (or the reverse) would change the totals
                candidates = candidates.filtered(lambda t: t.price_include == tax.price_include)
            candidates = candidates.sorted(lambda t: (
                t.price_include != tax.price_include, t.tax_scope != tax.tax_scope,
                bool(t.fiscal_position_ids) and fiscal_position not in t.fiscal_position_ids, t.sequence, t.id))
            for candidate in candidates:
                found = fiscal(candidate)
                if found:
                    result |= found
                    break
        return result

    def _om_ic_map_analytic(self, distribution, target):
        """The analytic distribution of a line, kept for the analytic accounts ``target`` may use."""
        self.ensure_one()
        if self.analytic_mode != 'keep' or not distribution:
            return False
        result = {}
        Analytic = self.env['account.analytic.account'].sudo()
        for key, value in distribution.items():
            ids = [int(i) for i in str(key).split(',') if i.isdigit()]
            accounts = Analytic.browse(ids).exists()
            if len(accounts) == len(ids) and all(not a.company_id or a.company_id == target for a in accounts):
                result[key] = value
        return result or False

    # ------------------------------------------------------------------
    # Screen
    # ------------------------------------------------------------------

    def action_om_ic_swap(self):
        """Exchange the company and the other company (and their journals and mappings)."""
        for rule in self:
            rule.write({
                'company_id': rule.target_company_id.id, 'target_company_id': rule.company_id.id,
                'target_sale_journal_id': rule.source_sale_journal_id.id,
                'target_purchase_journal_id': rule.source_purchase_journal_id.id,
                'source_sale_journal_id': rule.target_sale_journal_id.id,
                'source_purchase_journal_id': rule.target_purchase_journal_id.id,
            })
            for lines, field in ((rule.account_map_ids, 'account_id'), (rule.tax_map_ids, 'tax_id'),
                                 (rule.product_map_ids, 'product_id')):
                for line in lines:
                    line.write({'company_%s' % field: line['target_%s' % field].id,
                                'target_%s' % field: line['company_%s' % field].id})
        return True


class OmInterCompanyAccountMap(models.Model):
    _name = 'om.inter.company.account.map'
    _description = 'Inter-Company Account Mapping'

    rule_id = fields.Many2one('om.inter.company.rule', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='rule_id.company_id')
    target_company_id = fields.Many2one(related='rule_id.target_company_id')
    company_account_id = fields.Many2one(
        'account.account', string="Account of the Company", required=True,
        domain="[('company_ids', 'parent_of', company_id)]")
    target_account_id = fields.Many2one(
        'account.account', string="Account of the Other Company", required=True,
        domain="[('company_ids', 'parent_of', target_company_id)]")


class OmInterCompanyTaxMap(models.Model):
    _name = 'om.inter.company.tax.map'
    _description = 'Inter-Company Tax Mapping'

    rule_id = fields.Many2one('om.inter.company.rule', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='rule_id.company_id')
    target_company_id = fields.Many2one(related='rule_id.target_company_id')
    company_tax_id = fields.Many2one(
        'account.tax', string="Tax of the Company", required=True,
        domain="[('company_id', 'parent_of', company_id)]")
    target_tax_id = fields.Many2one(
        'account.tax', string="Tax of the Other Company", required=True,
        domain="[('company_id', 'parent_of', target_company_id)]")


class OmInterCompanyProductMap(models.Model):
    _name = 'om.inter.company.product.map'
    _description = 'Inter-Company Product Mapping'

    rule_id = fields.Many2one('om.inter.company.rule', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='rule_id.company_id')
    target_company_id = fields.Many2one(related='rule_id.target_company_id')
    company_product_id = fields.Many2one(
        'product.product', string="Product of the Company", required=True,
        domain="['|', ('company_id', '=', False), ('company_id', 'parent_of', company_id)]")
    target_product_id = fields.Many2one(
        'product.product', string="Product of the Other Company", required=True,
        domain="['|', ('company_id', '=', False), ('company_id', 'parent_of', target_company_id)]")
