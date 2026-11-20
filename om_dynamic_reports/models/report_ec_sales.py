from collections import defaultdict

from odoo import api, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)


class OmDynamicReportEcSales(models.AbstractModel):
    """EC Sales List: per customer of another country of the European Union
    with a VAT number, what was invoiced to it in the period, goods and services
    apart, the credit notes deducted; a customer opens its invoice lines.
    Offered to the companies of the European Union.
    """
    _name = 'om.dynamic.report.ec.sales'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic EC Sales List'

    _report_name = 'EC Sales List'
    _report_description = _lt("Sales to the customers of the other countries of the European Union.")
    _report_section = 'statements'
    _report_sequence = 7
    _report_icon = 'euro'

    @api.model
    def _om_report_title(self):
        return self.env._("EC Sales List")

    @api.model
    def _om_name_label(self, options):
        return self.env._("Customer")

    @api.model
    def _odr_eu_countries(self):
        europe = self.env.ref('base.europe', raise_if_not_found=False)
        return europe.country_ids if europe else self.env['res.country']


    @api.model
    def _om_filters(self):
        return self._odr_filters('partner_ids', 'journal_ids')

    @api.model
    def _om_choices(self):
        return [self._odr_target_move_choice()]

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'country', 'label': self.env._("Country"), 'type': 'char'},
            {'key': 'vat', 'label': self.env._("VAT Number"), 'type': 'char'},
            {'key': 'goods', 'label': self.env._("Goods"), 'type': 'monetary', 'drill': True},
            {'key': 'services', 'label': self.env._("Services"), 'type': 'monetary', 'drill': True},
            {'key': 'total', 'label': self.env._("Total"), 'type': 'monetary', 'drill': True},
        ]

    @api.model
    def _odr_ec_domain(self, options, partner=None):
        """The invoice lines of the period to the customers of the other countries of the Union with a VAT number."""
        countries = self._odr_eu_countries() - self.env.company.account_fiscal_country_id
        domain = self._odr_domain(options) + self._odr_period_domain(options) + [
            ('move_id.move_type', 'in', ('out_invoice', 'out_refund')),
            ('display_type', '=', 'product'),
            ('move_id.commercial_partner_id.country_id', 'in', countries.ids),
            ('move_id.commercial_partner_id.vat', '!=', False),
        ]
        if partner:
            domain.append(('move_id.commercial_partner_id', '=', partner.id))
        return domain

    @api.model
    def _odr_tree(self, options):
        if self.env.company.account_fiscal_country_id not in self._odr_eu_countries():
            # only the companies of the European Union file it
            return [], False
        sums = defaultdict(lambda: {'goods': 0.0, 'services': 0.0})
        rows = self.env['account.move.line']._read_group(
            self._odr_ec_domain(options), ['move_id', 'product_id', 'company_id'], ['balance:sum'])
        for move, product, company, balance in rows:
            kind = 'services' if product.type == 'service' else 'goods'
            # a sale is a credit: the amounts are shown positive, the credit notes negative
            sums[move.commercial_partner_id][kind] -= self._odr_convert(balance, company)
        nodes = []
        totals = {'goods': 0.0, 'services': 0.0, 'total': 0.0}
        for partner in sorted(sums, key=lambda partner: (partner.country_id.code or '', partner.name or '')):
            values = {**sums[partner], 'total': sums[partner]['goods'] + sums[partner]['services'],
                      'country': partner.country_id.code or '', 'vat': partner.vat or ''}
            for key in totals:
                totals[key] += values[key]
            node_id = 'partner-%s' % partner.id
            nodes.append(self._odr_node(node_id, partner.display_name, self._om_line(
                node_id, partner.display_name, values, kind='leaf', drill=True,
                open_record=('res.partner', partner.id))))
        return nodes, totals if nodes else False

    @api.model
    def _om_total(self, data, options):
        if not data.get('total'):
            return False
        return self._om_line('total', self.env._("Total"), data['total'], kind='total')

    @api.model
    def _om_cell_action(self, options, line_id, column_key):
        partner = self.env['res.partner'].browse(self._odr_line_id_part(line_id, 'partner') or [])
        domain = self._odr_ec_domain(options, partner or None)
        if column_key == 'goods':
            domain.append(('product_id.type', '!=', 'service'))
        elif column_key == 'services':
            domain.append(('product_id.type', '=', 'service'))
        return self._odr_journal_items_action(domain, partner.display_name or self.env._("EC Sales List"))
