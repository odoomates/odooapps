# Odoo 15 has no account_type selection on the accounts, nor a balance to create journal items with:
# the tests, written for the later versions, name the type of an account by the kind of Odoo 16

from odoo.tests import Form

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.accounting_pdf_reports.models.account_account import ACCOUNT_TYPE_KINDS

XMLID_BY_KIND = {kind: xmlid for xmlid, kind in ACCOUNT_TYPE_KINDS.items()}


def user_type(env, kind):
    """ :return: the values that give an account the account type of `kind` (e.g. 'asset_fixed') """
    return {'user_type_id': env.ref(XMLID_BY_KIND[kind]).id}


def debit_credit(balance):
    """ :return: the debit and the credit of a journal item of `balance` """
    return {'debit': balance if balance > 0.0 else 0.0, 'credit': -balance if balance < 0.0 else 0.0}


class OmAccountTestCommon(AccountTestInvoicingCommon):

    @classmethod
    def init_invoice(cls, move_type, partner=None, invoice_date=None, post=False, products=None, amounts=None,
                     taxes=None, company=False, currency=None):
        """ As in Odoo 16: an empty list of taxes is an invoice without taxes, not the default ones """
        move = super().init_invoice(move_type, partner=partner, invoice_date=invoice_date, post=False,
                                    products=products, amounts=amounts, taxes=taxes, company=company,
                                    currency=currency)
        if taxes is not None and not taxes:
            with Form(move) as move_form:
                for index in range(len(move_form.invoice_line_ids)):
                    with move_form.invoice_line_ids.edit(index) as line_form:
                        line_form.tax_ids.clear()
        if post:
            move.action_post()
        return move
