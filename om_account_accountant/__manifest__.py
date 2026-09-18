{
    'name': 'Odoo 20 Accounting Community',
    'version': '1.0.7',
    'category': 'Accounting',
    'summary': 'Accounting Reports, Asset Management and Budget, Recurring Payments, '
               'Lock Dates, Fiscal Year, Period Closing, Accounting Dashboard, Financial Reports, '
               'Cash Flow Statement, Cash Forecast, Customer Follow up Management, Bank Reconciliation, '
               'Cheque Printing, Automatic Currency Rates, Currency Revaluation, Bank Statement Import',
    'description': 'Odoo 20 Financial Reports, Asset Management and '
                   'Budget, Financial Reports, Cash Flow Statement, Cash Forecast, '
                   'Recurring Payments, Bank Reconciliation, Customer Follow Up Management, '
                   'Account Lock Date, Fiscal Year and Period Closing, Cheque Printing, '
                   'Automatic Currency Rates, Accounting Dashboard',
    'live_test_url': 'https://www.youtube.com/c/OdooMates',
    'sequence': '1',
    'author': 'Odoo Mates, Odoo SA',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': [
        'accounting_pdf_reports',
        'om_account_asset',
        'om_account_budget',
        'om_fiscal_year',
        'om_recurring_payments',
        'om_account_daily_reports',
        'om_account_followup',
        'om_account_reconcile',
        'om_account_cash_forecast',
        'om_account_check_printing',
        'om_currency_rate_update',
        'om_currency_revaluation',
        'om_account_bank_statement_import',
        'om_spreadsheet_account',
        'om_spreadsheet_account_asset',
        'om_spreadsheet_account_budget',
        'om_spreadsheet_account_followup',
    ],
    'data': [
        'security/group.xml',
        'views/menu.xml',
        'views/settings.xml',
        'views/account_tag.xml',
        'views/res_partner.xml',
        'views/account_bank_statement.xml',
        'views/payment_method.xml',
        'views/reconciliation.xml',
        'views/account_journal.xml',
    ],
    'application': True,
    'images': ['static/description/banner.gif'],
}

