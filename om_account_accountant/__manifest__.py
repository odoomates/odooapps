{
    'name': 'Odoo 15 Accounting',
    'version': '6.4.0',
    'category': 'Accounting',
    'summary': 'Annual Report, Bank Reconciliation Statement, Accounting Reports, '
               'Asset Management and Budget, Recurring Payments, Customer Credit Limit, '
               'Lock Dates, Fiscal Year, Period Closing, Financial Reports, '
               'Cash Flow Statement, Cash Forecast, Customer Follow up Management, '
               'Cheque Printing, Automatic Currency Rates, Currency Revaluation, Bank Statement Import',
    'description': 'Odoo 15 Financial Reports, Asset Management and '
                   'Budget, Financial Reports, Cash Flow Statement, Cash Forecast, '
                   'Recurring Payments, Customer Credit Limit, Customer Follow Up Management, '
                   'Account Lock Date, Fiscal Year and Period Closing, Cheque Printing, '
                   'Automatic Currency Rates, Bank Statement Import',
    'live_test_url': 'https://www.youtube.com/watch?v=6gB-05E5kNg',
    'sequence': '1',
    'website': 'https://www.odoomates.tech',
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
        'om_account_bank_statement_import',
        'om_credit_limit',
        'om_account_daily_reports',
        'om_account_followup',
        'om_account_cash_forecast',
        'om_account_check_printing',
        'om_currency_rate_update',
        'om_currency_revaluation',
    ],
    'excludes': ['account_accountant'],
    'data': [
        'security/group.xml',
        'views/menu.xml',
        'views/review_menu.xml',
        'views/settings.xml',
        'views/account_type.xml',
        'views/account_group.xml',
        'views/account_tag.xml',
        'views/res_partner.xml',
        'views/account_bank_statement.xml',
        'views/payment_method.xml',
        'views/reconciliation.xml',
        'views/account_journal.xml',
        'views/account_coa_template.xml',
        'views/fiscal_position_template.xml',
    ],
    'application': True,
    'images': ['static/description/banner.gif'],
}
