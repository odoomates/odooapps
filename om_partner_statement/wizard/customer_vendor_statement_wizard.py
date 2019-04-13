# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from datetime import date, datetime
from odoo import api, fields, models


class CustomervendorStatementWizard(models.TransientModel):
    """Customer vendor Statement wizard."""

    _name = 'customer.vendor.statement.wizard'
    _description = 'Customer vendor Statement Wizard'

    company_id = fields.Many2one(
        comodel_name='res.company',
        default=lambda self: self.env.user.company_id,
        string='Company'
    )

    date_start = fields.Date(required=True,
                             default=datetime.now().strftime('%Y-01-01'))
    date_end = fields.Date(required=True,
                           default=fields.Date.to_string(date.today()))
    show_aging_buckets = fields.Boolean(string='Include Aging Buckets',
                                        default=False)
    number_partner_ids = fields.Integer(
        default=lambda self: len(self._context['active_ids'])
    )
    filter_partners_non_due = fields.Boolean(
        string='Don\'t show partners with no due entries', default=False)
    report_type = fields.Selection([('receivable', 'Receivable'),
                              ('payable', 'Payable'),
                              ('receivable_and_payable', 'Receivable and Payable')],
                             'Report Type', default="receivable", required=True
                             )

    @api.multi
    def button_export_pdf(self):
        self.ensure_one()
        return self._export()

    def _prepare_vendor_statement(self):
        self.ensure_one()
        return {
            'date_start': self.date_start,
            'date_end': self.date_end,
            'company_id': self.company_id.id,
            'partner_ids': self._context['active_ids'],
            'show_aging_buckets': self.show_aging_buckets,
            'filter_partners_non_due': self.filter_partners_non_due,
            'report_type': self.report_type,
        }

    def _export(self):
        """Export to PDF."""

        data = self.read(['date_start', 'date_end', 'report_type', 'show_aging_buckets', 'filter_partners_non_due'])[0]
        data.update({'partner_ids': self._context['active_ids']})
        data.update({'company_id': self.company_id.id})
        return self.env.ref('om_partner_statement.action_print_customer_vendor_statement').report_action(self, data=data)
