from odoo import fields, models

SALTEDGE_CREDENTIAL_GROUPS = 'base.group_system,account.group_account_manager'


class ResCompany(models.Model):
    _inherit = 'res.company'

    saltedge_app_id = fields.Char(string='Salt Edge App ID', groups=SALTEDGE_CREDENTIAL_GROUPS, copy=False)
    saltedge_secret = fields.Char(string='Salt Edge Secret', groups=SALTEDGE_CREDENTIAL_GROUPS, copy=False)
    saltedge_private_key = fields.Char(
        string='Salt Edge Private Key', groups=SALTEDGE_CREDENTIAL_GROUPS, copy=False,
        help="The RSA private key (PEM) whose public key is in your Salt Edge dashboard. When set, every request "
             "is signed: Salt Edge requires it for the applications in Live status.")
    saltedge_include_fake = fields.Boolean(
        string='Salt Edge Test Banks', groups=SALTEDGE_CREDENTIAL_GROUPS,
        help="Also offer the fake and sandbox banks of Salt Edge, to try the connection without a real bank.")
    saltedge_customer_id = fields.Char(string='Salt Edge Customer ID', groups=SALTEDGE_CREDENTIAL_GROUPS,
                                       copy=False, readonly=True)
    saltedge_customer_identifier = fields.Char(string='Salt Edge Customer Identifier',
                                               groups=SALTEDGE_CREDENTIAL_GROUPS, copy=False, readonly=True)
