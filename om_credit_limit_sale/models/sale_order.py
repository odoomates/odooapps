from collections import defaultdict

from odoo import _, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _check_credit_limit(self):
        """ A sales order going over the credit limit is refused, unless the user is allowed to override it: the
        override is then logged on the order. An online payment or a portal signature runs as superuser or as a
        portal user: the customer has already acted, and nobody is there to deal with the refusal. """
        if self.env.su or not self.env.user._is_internal():
            return
        can_override = self.env.user.has_group('om_credit_limit.group_credit_limit_override')
        # the orders confirmed together add up: the customer owes them all at the end
        confirmed_together = defaultdict(float)
        for order in self:
            company = order.company_id
            if order.state not in ('draft', 'sent') or not company.credit_limit_block_sale \
                    or not company.account_use_credit_limit:
                continue
            order = order.with_company(company)
            partner = order.partner_id.commercial_partner_id
            amount = order.amount_total / order.currency_rate
            # what the customer owes is read again: the documents posted since are part of it
            partner.invalidate_recordset(['credit', 'credit_to_invoice'])
            warning = self.env['account.move']._build_credit_warning_message(
                order.sudo(), current_amount=amount + confirmed_together[partner])
            confirmed_together[partner] += amount
            if not warning:
                continue
            if not can_override:
                raise UserError(_(
                    '%(warning)s\n\nThis sales order cannot be confirmed: ask an accounting manager to confirm it, '
                    'or collect what the customer owes first.', warning=warning,
                ))
            order.message_post(body=_('Confirmed over the credit limit of the customer.\n%(warning)s',
                                      warning=warning))

    def action_confirm(self):
        self._check_credit_limit()
        return super().action_confirm()
