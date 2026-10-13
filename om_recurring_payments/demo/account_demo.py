import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.addons.account.models.chart_template import template

_logger = logging.getLogger(__name__)

MODULE = 'om_recurring_payments'


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _om_recurring_xmlid(self, name):
        """ The xmlid of a demo record of the company, owned by the module: uninstalling it removes its demo """
        return f'{MODULE}.{self.env.company.id}_{name}'

    def _om_recurring_demo_partner_id(self, xmlid):
        """ The id of a demo partner: given by its id, the field is not delayed by the loading of the demo
        partners of the other modules. """
        return (self.env.ref(xmlid, raise_if_not_found=False) or self.env['res.partner']).id

    def _om_recurring_demo_missing(self, data):
        """ The demo records not created yet: the existing ones are left as they are. """
        return {xmlid: values for xmlid, values in data.items() if not self.ref(xmlid, raise_if_not_found=False)}

    def _om_recurring_demo_journal(self):
        company = self.env.company
        return self.ref('bank', raise_if_not_found=False) or self.env['account.journal'].search([
            *self.env['account.journal']._check_company_domain(company), ('type', '=', 'bank')], limit=1)

    @template(model='account.recurring.template', demo=True)
    def _get_om_recurring_demo_1_template(self, template_code):
        company = self.env.company
        journal = self._om_recurring_demo_journal()
        if company.parent_id or not journal:
            return {}
        return self._om_recurring_demo_missing({
            self._om_recurring_xmlid('om_recurring_template_monthly'): {
                'name': 'Monthly, paid on the date',
                'company_id': company.id,
                'journal_id': journal.id,
                'recurring_period': 'months',
                'recurring_interval': 1,
                'journal_state': 'posted',
                'state': 'done',
                'description': 'Rent, leases and subscriptions paid every month: the payments are posted.',
            },
            self._om_recurring_xmlid('om_recurring_template_quarterly'): {
                'name': 'Quarterly, to review',
                'company_id': company.id,
                'journal_id': journal.id,
                'recurring_period': 'months',
                'recurring_interval': 3,
                'journal_state': 'draft',
                'state': 'done',
                'description': 'Payments every three months, created as drafts to check before posting.',
            },
        })

    @template(model='recurring.payment', demo=True)
    def _get_om_recurring_demo_2_payment(self, template_code):
        company = self.env.company
        journal = self._om_recurring_demo_journal()
        if company.parent_id or not journal:
            return {}
        today = fields.Date.context_today(self)
        payments = {
            self._om_recurring_xmlid('om_recurring_payment_rent'): {
                'partner_id': self._om_recurring_demo_partner_id('base.res_partner_3'),
                'company_id': company.id,
                'template_id': self._om_recurring_xmlid('om_recurring_template_monthly'),
                'journal_id': journal.id,
                'currency_id': company.currency_id.id,
                'payment_type': 'outbound',
                'amount': 850.0,
                'date_begin': today + relativedelta(months=-4, day=1),
                'date_end': today + relativedelta(months=7, day=1),
                'description': 'Office furniture lease',
            },
            self._om_recurring_xmlid('om_recurring_payment_maintenance'): {
                'partner_id': self._om_recurring_demo_partner_id('base.res_partner_12'),
                'company_id': company.id,
                'template_id': self._om_recurring_xmlid('om_recurring_template_quarterly'),
                'journal_id': journal.id,
                'currency_id': company.currency_id.id,
                'payment_type': 'inbound',
                'amount': 1200.0,
                'date_begin': today + relativedelta(months=1, day=1),
                'date_end': today + relativedelta(months=22, day=1),
                'description': 'Maintenance contract, invoiced every quarter',
            },
        }
        # the partner is required: no demo partner, no demo recurring payment
        return self._om_recurring_demo_missing({
            xmlid: values for xmlid, values in payments.items() if values['partner_id']})

    def _om_recurring_post_load_demo(self):
        """ Confirm the monthly demo recurring payment and pay its lines due up to today. The quarterly one stays
        a draft. Called again on the companies already done, it changes nothing. """
        recurring = self.ref(self._om_recurring_xmlid('om_recurring_payment_rent'), raise_if_not_found=False)
        if not recurring or recurring.state != 'draft':
            return
        today = fields.Date.context_today(self)
        try:
            with self.env.cr.savepoint():
                recurring.action_done()
                due_lines = recurring.line_ids.filtered(lambda line: line.state == 'draft' and line.date < today)
                for line in due_lines.sorted('date'):
                    line.with_company(line.company_id).action_create_payment()
        except Exception:  # noqa: BLE001 the demo is not worth failing the installation
            _logger.exception('Error while confirming the demo recurring payment of %s', self.env.company.name)

    def _post_load_demo_data(self, template_code):
        super()._post_load_demo_data(template_code)
        self._om_recurring_post_load_demo()

    @api.model
    def _om_recurring_post_load_demo_companies(self):
        for company in self.env['res.company'].search([('chart_template', '!=', False)], order='parent_path'):
            self.with_company(company).with_context(allowed_company_ids=company.ids)._om_recurring_post_load_demo()


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def write(self, vals):
        # the demo data of the module is loaded on the companies with a chart when the module is set installed
        installing = len(self) == 1 and self.name == MODULE and self.state not in (
            'installed', 'to upgrade', 'to remove')
        res = super().write(vals)
        if installing and self.state == 'installed' and self.demo:
            self.env['account.chart.template'].sudo()._om_recurring_post_load_demo_companies()
        return res
