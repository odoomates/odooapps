from odoo import _, api, models


class ReportCashForecast(models.AbstractModel):
    _inherit = 'report.om_account_cash_forecast.report_cash_forecast'

    @api.model
    def _get_row_keys(self):
        receipts, payments = super()._get_row_keys()
        # before the items entered by hand
        index = payments.index('expected_out') if 'expected_out' in payments else len(payments)
        payments[index:index] = ['loans_out', 'leases_out']
        return receipts, payments

    @api.model
    def _get_row_labels(self):
        return {
            **super()._get_row_labels(),
            'loans_out': _('Loan instalments'),
            'leases_out': _('Lease payments not yet billed'),
        }

    @api.model
    def _get_forecast_items(self, wizard, date_to):
        """ The instalments of the running loans still to pay, net of the tax withheld, and the payments of the
        running leases not billed yet, taxes of the bills included, on their due dates. The bills already
        created are vendor bills of the forecast. """
        items = super()._get_forecast_items(wizard, date_to)
        company = wizard.company_id
        currency = company.currency_id
        lines = self.env['account.loan.line'].search([
            ('company_id', 'child_of', company.id),
            ('state', '=', 'draft'),
            ('loan_id.state', '=', 'running'),
            ('date', '<=', date_to),
        ])
        for line in lines:
            loan = line.loan_id
            if loan.loan_type == 'lease':
                amount = self._lease_payment_with_taxes(line)
                row = 'leases_out'
            else:
                amount = line.net_amount
                row = 'loans_out'
            if loan.currency_id.is_zero(amount):
                continue
            items.append({
                'date': line.date,
                'amount': -loan.currency_id._convert(amount, currency, company, wizard.date_from),
                'row': row,
                'partner': loan.partner_id.commercial_partner_id.name or loan.name,
            })
        return items

    @api.model
    def _lease_payment_with_taxes(self, line):
        """ What the bill of the lease payment `line` will ask: the principal and the interest with the taxes of
        the bills, the interest less the tax withheld, as the bill splits them. """
        loan = line.loan_id
        currency = loan.currency_id
        total = loan.bill_tax_ids.compute_all(line.principal, currency=currency)['total_included']
        total += (loan.bill_tax_ids | loan.withholding_tax_id).compute_all(
            line.interest, currency=currency)['total_included']
        return currency.round(total)
