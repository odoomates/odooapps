import logging

_logger = logging.getLogger(__name__)

MODULE = 'accounting_pdf_reports'

# The Balance Sheet as it was shipped up to 1.x. A database where it still stands as it was gets the new one;
# a database where it was adapted keeps what it has, so that nobody's report changes under them.
KEPT_PARAMETER = 'accounting_pdf_reports.balance_sheet_kept'

STOCK_NODES = {
    'account_financial_report_assets0': {
        'name': 'Assets',
        'sign': '1',
        'type': 'account_type',
        'types': [
            {'asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current', 'asset_prepayments',
             'asset_fixed'},
            # 1.0.x, where the prepayments were nested in the assets by mistake
            {'asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current', 'asset_fixed'},
        ],
    },
    'account_financial_report_liabilitysum0': {
        'name': 'Liability',
        'sign': '1',
        'type': 'sum',
        'types': None,
    },
    'account_financial_report_liability0': {
        'name': 'Liability',
        'sign': '1',
        'type': 'account_type',
        'types': [
            {'liability_payable', 'equity', 'equity_unaffected', 'liability_current', 'liability_non_current'},
            # 1.0.x, before the current year earnings were added to it
            {'liability_payable', 'equity', 'liability_current', 'liability_non_current'},
        ],
    },
    'account_financial_report_profitloss_toreport0': {
        'name': 'Profit (Loss) to report',
        'sign': '1',
        'type': 'account_report',
        'types': None,
    },
}


def _nodes(cr):
    """ :return: {xml id: (id, name, sign, type)} of the Balance Sheet records of the module """
    cr.execute("""
        SELECT data.name, report.id, report.name->>'en_US', report.sign, report.type
          FROM ir_model_data data
          JOIN account_financial_report report ON report.id = data.res_id
         WHERE data.module = %s AND data.model = 'account.financial.report' AND data.name IN %s
    """, [MODULE, tuple(STOCK_NODES)])
    return {row[0]: row[1:] for row in cr.fetchall()}


def _account_types(cr, report_id):
    cr.execute("""
        SELECT account_type.type
          FROM account_account_financial_report_type rel
          JOIN account_account_type account_type ON account_type.id = rel.account_type_id
         WHERE rel.report_id = %s
    """, [report_id])
    return {row[0] for row in cr.fetchall()}


def _is_stock(cr, nodes):
    """ :return: whether the Balance Sheet is still the one the module shipped """
    for xml_id, expected in STOCK_NODES.items():
        if xml_id not in nodes:
            # a node was removed: the report is not the one of the module any more
            return False
        report_id, name, sign, report_type = nodes[xml_id]
        if (name, sign, report_type) != (expected['name'], expected['sign'], expected['type']):
            return False
        if expected['types'] is not None and _account_types(cr, report_id) not in expected['types']:
            return False
    return True


def migrate(cr, version):
    """ Upgrade to 2.0.0: the Balance Sheet tells the liabilities from the equity, and prints them positive.

    Up to 1.x the report had a Liability inside a Liability, held the equity accounts among the liabilities,
    and printed both negative because their balance is credit. This script decides whether the database may
    receive the new report:

    * the Balance Sheet still as the module shipped it is updated, and the amounts of the liabilities and of
      the equity change sign, which post-migrate.py says in the log
    * a Balance Sheet adapted by the customer is kept exactly as it is: its records are set no-update, so the
      new definition does not overwrite them, and post-migrate.py takes the new Equity node out of it
    """
    if not version:
        return

    nodes = _nodes(cr)
    if not nodes:
        return
    if _is_stock(cr, nodes):
        _logger.info('accounting_pdf_reports: the Balance Sheet is the one of the module, it is updated to 2.0.0')
        return

    cr.execute("""
        UPDATE ir_model_data
           SET noupdate = true
         WHERE module = %s AND model = 'account.financial.report' AND name IN %s
    """, [MODULE, tuple(STOCK_NODES)])
    cr.execute("""
        INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
             VALUES (%s, '1', 1, now(), 1, now())
        ON CONFLICT (key) DO UPDATE SET value = '1'
    """, [KEPT_PARAMETER])
    _logger.warning(
        'accounting_pdf_reports: your Balance Sheet was adapted, so it is kept as it is and the report of '
        '2.0.0 is not applied to it. The new report tells the liabilities from the equity and prints them '
        'positive: to take it, edit your report in Accounting > Configuration > Accounting > Financial Reports.')
