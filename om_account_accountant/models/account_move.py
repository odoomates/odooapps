from collections import defaultdict

from odoo import _, api, models
from odoo.exceptions import UserError

# the documents that add to what a customer owes
CREDIT_LIMIT_TYPES = ('out_invoice', 'out_receipt')


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model
    def _get_invoice_in_payment_state(self):
        return 'in_payment'

    def _check_credit_limit(self):
        """ A customer invoice going over the credit limit of the customer is refused, unless the user is
        allowed to override it: the override is then logged on the invoice. """
        can_override = self.env.user.has_group('om_account_accountant.group_credit_limit_override')
        # the invoices posted together add up: the customer owes them all at the end
        posted_together = defaultdict(float)
        for move in self:
            company = move.company_id
            if move.move_type not in CREDIT_LIMIT_TYPES or move.state != 'draft' \
                    or not company.credit_limit_block or not company.account_use_credit_limit:
                continue
            move = move.with_company(company)
            partner = move.partner_id.commercial_partner_id
            if not partner:
                continue
            # what the customer owes is read again: the invoices posted since are part of it
            partner.invalidate_recordset(['credit', 'credit_to_invoice'])
            current_amount = move.amount_total_signed + posted_together[partner]
            posted_together[partner] += move.amount_total_signed
            warning = move._build_credit_warning_message(
                move,
                current_amount=current_amount,
                exclude_amount=move._get_partner_credit_warning_exclude_amount(),
            )
            if not warning:
                continue
            if not can_override:
                raise UserError(_(
                    '%(warning)s\n\nThis invoice cannot be posted: ask an accounting manager to post it, or '
                    'collect what the customer owes first.', warning=warning,
                ))
            move.message_post(body=_('Posted over the credit limit of the customer.\n%(warning)s',
                                     warning=warning))

    def _post(self, soft=True):
        self._check_credit_limit()
        return super()._post(soft)
