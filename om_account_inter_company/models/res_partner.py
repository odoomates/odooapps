from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    om_ic_company_id = fields.Many2one(
        'res.company', string="Group Company", compute='_compute_om_ic_company_id', store=True, readonly=False,
        index='btree_not_null',
        help="The company of the group this partner is: its invoices and bills follow the inter-company rules "
             "and its balances show in the Inter-Company Balances report. Set on the partner of each company; "
             "set it on another partner standing for a company of the group.")
    om_inter_company = fields.Boolean(
        string="Inter-Company Partner", compute='_compute_om_inter_company', search='_search_om_inter_company')

    @api.depends('ref_company_ids')
    def _compute_om_ic_company_id(self):
        for partner in self:
            companies = partner.sudo().ref_company_ids
            if companies:
                partner.om_ic_company_id = companies[0]
            elif not partner.om_ic_company_id:
                partner.om_ic_company_id = False

    @api.depends('om_ic_company_id', 'commercial_partner_id.om_ic_company_id')
    def _compute_om_inter_company(self):
        for partner in self:
            partner.om_inter_company = bool(partner._om_ic_company())

    def _search_om_inter_company(self, operator, value):
        if operator != 'in':
            return NotImplemented
        return ['|', ('om_ic_company_id', '!=', False), ('commercial_partner_id.om_ic_company_id', '!=', False)]

    def _om_ic_company(self):
        """The group company this partner (or its company) stands for."""
        self.ensure_one()
        partner = self.sudo()
        return partner.om_ic_company_id or partner.commercial_partner_id.om_ic_company_id
