from odoo import models, _
from odoo.exceptions import RedirectWarning

from .res_company import CHECK_FORMAT_LAYOUT


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _get_check_layout(self):
        return self.journal_id.bank_check_printing_layout or self.company_id.account_check_printing_layout

    def do_print_checks(self):
        if self[:1]._get_check_layout() != CHECK_FORMAT_LAYOUT:
            return super().do_print_checks()
        check_format = self.journal_id[:1]._get_check_format()
        if not check_format:
            action = self.env.ref('om_account_check_printing.action_check_format')
            raise RedirectWarning(
                _('Create a cheque format and choose it on the bank journal %s.', self.journal_id[:1].name),
                action.id, _('Go to the cheque formats'))
        self.write({'is_sent': True})
        return self.env.ref(CHECK_FORMAT_LAYOUT).with_context(om_check_format_id=check_format.id).report_action(self, config=False)

    def _om_check_pages(self, check_format):
        """ :return: the pages printed for the payment: the cheque on the first one, VOID on the next ones when
                     the stub spills over """
        self.ensure_one()
        pages = []
        stub_pages = (self._check_make_stub_pages() if check_format.print_stub else None) or [False]
        for index, stub_lines in enumerate(stub_pages):
            pages.append({
                'values': check_format._get_field_values(
                    self.partner_id.name, self.amount, self.currency_id, self.date, self.memo, self.check_number,
                    self.company_id, void=index > 0),
                'stub_lines': stub_lines or [],
                'partner_name': self.partner_id.name,
            })
        return pages
