from odoo import api, fields, models


class BillOcrProfile(models.Model):
    """ What the bills of a vendor taught: where the vendor prints its fields, how it writes its dates, and the
    account and the taxes its bills are booked on. Learned when a read bill is posted, used on the next one. """
    _name = 'om.bill.ocr.profile'
    _description = "Vendor Bill Recognition Profile"
    _order = 'bill_count desc, id desc'
    _rec_name = 'partner_id'
    _check_company_auto = True

    partner_id = fields.Many2one('res.partner', string="Vendor", required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company,
                                 ondelete='cascade')
    account_id = fields.Many2one('account.account', string="Account", check_company=True,
                                 help="The account of the lines of this vendor's bills.")
    tax_ids = fields.Many2many('account.tax', string="Taxes", check_company=True,
                               domain="[('type_tax_use', '=', 'purchase')]")
    product_id = fields.Many2one('product.product', string="Product", check_company=True,
                                 help="Put on the line of a bill read as a single line.")
    line_mode = fields.Selection([
        ('lines', "Line Items"),
        ('single', "One Line"),
    ], string="Lines", default='lines', required=True,
        help="Line Items: the lines of the bill are read, and kept when they add up to its untaxed amount, "
             "else one line is made. One Line: always one line with the untaxed amount.")
    date_order = fields.Selection([
        ('dmy', "Day / Month / Year"),
        ('mdy', "Month / Day / Year"),
    ], string="Date Order", help="How the vendor prints its dates, when a date such as 03/04 could be read "
                                 "both ways. Empty: the date format of the language of the user.")
    anchor_ref = fields.Char(string="Bill Number Label")
    anchor_invoice_date = fields.Char(string="Bill Date Label")
    anchor_invoice_date_due = fields.Char(string="Due Date Label")
    anchor_amount_total = fields.Char(string="Total Label")
    match_keys = fields.Text(string="Recognized By",
                             help="The tax numbers, bank accounts, email domains and letterhead lines read on the "
                                  "bills of this vendor, one per line: a bill showing one of them is this "
                                  "vendor's.")
    bill_count = fields.Integer(string="Bills Learned From", readonly=True)
    last_learned = fields.Date(readonly=True)

    _partner_company_unique = models.Constraint(
        'unique(partner_id, company_id)',
        "A vendor has one recognition profile per company.",
    )

    @api.model
    def _for_partner(self, partner, company, create=False):
        partner = partner.commercial_partner_id
        profile = self.search([('partner_id', '=', partner.id), ('company_id', '=', company.id)], limit=1)
        if not profile and create:
            profile = self.create({'partner_id': partner.id, 'company_id': company.id})
        return profile

    def _anchors(self):
        self.ensure_one()
        return {
            'ref': self.anchor_ref,
            'invoice_date': self.anchor_invoice_date,
            'invoice_date_due': self.anchor_invoice_date_due,
            'amount_total': self.anchor_amount_total,
        }

    def _match_keys(self):
        return {key.strip() for key in (self.match_keys or '').splitlines() if key.strip()}

    def _add_match_keys(self, keys):
        self.ensure_one()
        known = self._match_keys()
        new = [key for key in keys if key and key not in known]
        if new:
            # the most recent keys first, and not an endless list
            self.match_keys = '\n'.join((new + sorted(known))[:30])
