import logging

from dateutil.relativedelta import relativedelta

from odoo import Command, fields, models

from odoo.addons.account.models.chart_template import template

from ..models.res_company import CHECK_FORMAT_LAYOUT

_logger = logging.getLogger(__name__)

MODULE = 'om_account_check_printing'


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _om_check_demo_xmlid(self, name, company=None):
        return '%s.%s_%s' % (MODULE, (company or self.env.company).id, name)

    def _om_check_demo_method_line(self, journal):
        return journal.outbound_payment_method_line_ids.filtered(lambda line: line.code == 'check_printing')[:1]

    @template(model='account.journal', demo=True)
    def _get_demo_data_om_check_printing_journal(self, template_code):
        """ The bank journal prints its cheques with the format of the country of the company """
        company = self.env.company
        if not self.ref('bank', raise_if_not_found=False):
            return {}
        check_format = (
            self.env['account.check.format'].search([
                ('country_ids', 'in', company.country_id.ids),
                '|', ('company_id', '=', False), ('company_id', '=', company.id),
            ], limit=1)
            or self.env.ref('om_account_check_printing.check_format_a4_top', raise_if_not_found=False)
        )
        if not check_format:
            return {}
        return {
            'bank': {
                'bank_check_printing_layout': CHECK_FORMAT_LAYOUT,
                'check_format_id': check_format.id,
            },
        }

    @template(model='account.move', demo=True)
    def _get_demo_data_om_check_printing_bill(self, template_code):
        """ A vendor bill paid by cheque in `_om_check_demo_post_load`, listed on the stub of the cheque """
        company = self.env.company
        journal = self.ref('bank', raise_if_not_found=False)
        if not journal or not self._om_check_demo_method_line(journal):
            return {}
        today = fields.Date.context_today(self)
        return {
            self._om_check_demo_xmlid('demo_bill_cheque'): {
                'move_type': 'in_invoice',
                'partner_id': 'base.res_partner_1',
                'invoice_date': (today - relativedelta(days=12)).strftime('%Y-%m-%d'),
                'ref': 'WC-%s-0815' % today.year,
                'company_id': company.id,
                'invoice_line_ids': [
                    Command.create({'name': 'Oak office desks', 'quantity': 4, 'price_unit': 312.5}),
                    Command.create({'name': 'Delivery and assembly', 'quantity': 1, 'price_unit': 145.0}),
                ],
            },
        }

    @template(model='account.payment', demo=True)
    def _get_demo_data_om_check_printing_payment(self, template_code):
        """ A vendor payment by cheque without a bill, e.g. an advance """
        company = self.env.company
        journal = self.ref('bank', raise_if_not_found=False)
        method_line = journal and self._om_check_demo_method_line(journal)
        if not method_line:
            return {}
        today = fields.Date.context_today(self)
        return {
            self._om_check_demo_xmlid('demo_payment_cheque'): {
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'partner_id': 'base.res_partner_10',
                'amount': 480.0,
                'date': (today - relativedelta(days=1)).strftime('%Y-%m-%d'),
                'memo': 'Advance on the maintenance contract',
                'journal_id': journal.id,
                'payment_method_line_id': method_line.id,
                'company_id': company.id,
            },
        }

    def _post_load_demo_data(self, template_code):
        super()._post_load_demo_data(template_code)
        self._om_check_demo_post_load(self.env.company)

    def _om_check_demo_post_load(self, company):
        """ Post the demo bill, pay it by cheque and post the demo payment: two cheques ready to print.
        Idempotent: only what was not done yet is done. """
        self = self.with_company(company)  # noqa: PLW0642
        journal = self.ref('bank', raise_if_not_found=False)
        method_line = journal and self._om_check_demo_method_line(journal)
        if not method_line:
            return
        try:
            with self.env.cr.savepoint():
                bill = self.env.ref(self._om_check_demo_xmlid('demo_bill_cheque', company), raise_if_not_found=False)
                if bill and bill.state == 'draft':
                    bill.action_post()
                if bill and bill.state == 'posted' and bill.payment_state == 'not_paid':
                    self.env['account.payment.register'].with_context(
                        active_model='account.move', active_ids=bill.ids,
                    ).create({
                        'journal_id': journal.id,
                        'payment_method_line_id': method_line.id,
                        'payment_date': fields.Date.context_today(self) - relativedelta(days=2),
                    })._create_payments()
                payment = self.env.ref(
                    self._om_check_demo_xmlid('demo_payment_cheque', company), raise_if_not_found=False)
                if payment and payment.state == 'draft':
                    payment.action_post()
        except Exception:  # noqa: BLE001 - the demo data of the other modules must still load
            _logger.exception('Error while completing the cheque printing demo data of %s', company.name)


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def write(self, vals):
        """ When the module is installed with demo data on companies that already have a chart, the
        accounting module loads its demo templates once the module is installed: complete them then. """
        was_installed = len(self) == 1 and self.state in ('installed', 'to upgrade', 'to remove')
        res = super().write(vals)
        if len(self) == 1 and self.name == MODULE and not was_installed and self.state == 'installed' and self.demo:
            for company in self.env['res.company'].search([('chart_template', '!=', False)], order='parent_path'):
                self.env['account.chart.template'].with_company(company)._om_check_demo_post_load(company)
        return res
