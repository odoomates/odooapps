import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

MODULE = 'accounting_pdf_reports'
KEPT_PARAMETER = 'accounting_pdf_reports.balance_sheet_kept'
EQUITY_XML_ID = 'account_financial_report_equity0'
EQUITY_ACCOUNTS_XML_ID = 'account_financial_report_equity_accounts0'


def migrate(cr, version):
    """ Upgrade to 2.0.0: leave the Balance Sheet of the customer alone, or say what changed in it.

    pre-migrate.py has set the parameter when the report was adapted by the customer and has to be kept. The
    Equity node of 2.0.0, with its Capital and Reserves, was created by the data of the module all the same, so
    it is taken out of the report here: adding it to a report whose liabilities already hold the equity accounts
    would count the equity twice. The Profit (Loss) to report of the customer stays where it was, as its record
    was set no-update.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    kept = env['ir.config_parameter'].sudo().get_bool(KEPT_PARAMETER)

    if not kept:
        _logger.info(
            'accounting_pdf_reports: the Balance Sheet of 2.0.0 tells the liabilities from the equity and '
            'prints both positive. The amounts of the liabilities, of the equity and of the profit of the '
            'period now come out positive where they used to come out negative: the report reads as a '
            'balance sheet is read, and nothing in the accounts has changed.')
        return

    equity = env.ref(f'{MODULE}.{EQUITY_XML_ID}', raise_if_not_found=False)
    if equity:
        equity.parent_id = False
        data = env['ir.model.data'].search([
            ('module', '=', MODULE), ('model', '=', 'account.financial.report'),
            ('name', 'in', (EQUITY_XML_ID, EQUITY_ACCOUNTS_XML_ID)),
        ])
        # never put back into the report of the customer by a later update of the module
        data.noupdate = True
        _logger.warning(
            'accounting_pdf_reports: the Equity node of 2.0.0 was taken out of your Balance Sheet, which is '
            'kept as you adapted it. It stays available in Accounting > Configuration > Accounting > '
            'Financial Reports if you want to add it yourself.')
    env['ir.config_parameter'].sudo().set_bool(KEPT_PARAMETER, None)
