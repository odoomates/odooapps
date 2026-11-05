from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestCompanyNotice(AccountTestInvoicingCommon):

    WIZARDS = ('account.balance.report', 'account.report.general.ledger', 'account.report.partner.ledger',
               'account.aged.trial.balance', 'account.tax.report.wizard', 'account.cash.flow.report',
               'accounting.report')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.other = cls.company_data_2['company'] if getattr(cls, 'company_data_2', None) \
            else cls.setup_other_company()['company']
        cls.env.user.company_ids |= cls.other

    def _notice(self, *companies):
        env = self.env(context=dict(self.env.context, allowed_company_ids=[company.id for company in companies]))
        # what the form opens with
        return {model: env[model].default_get(['company_notice']).get('company_notice') for model in self.WIZARDS}

    def test_no_notice_with_one_company(self):
        self.assertFalse(any(self._notice(self.company).values()))

    def test_notice_names_the_active_company(self):
        for model, notice in self._notice(self.company, self.other).items():
            self.assertIn(self.company.name, notice, model)
        for model, notice in self._notice(self.other, self.company).items():
            self.assertIn(self.other.name, notice, model)

    def test_the_form_opens_with_it(self):
        env = self.env(context=dict(self.env.context, allowed_company_ids=[self.company.id, self.other.id]))
        form = Form(env['account.balance.report'])
        self.assertIn(self.company.name, form.company_notice)

    def test_every_form_shows_it(self):
        for model in self.WIZARDS:
            self.assertIn('company_notice', self.env[model].get_view(view_type='form')['arch'], model)
