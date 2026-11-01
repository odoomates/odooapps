# Part of om_aed_currency_symbol (Odoo Mates). License: LGPL-3.
{
    'name': 'Odoo 20 UAE Dirham Symbol (AED)',
    'version': '1.0',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'category': 'Accounting/Localizations',
    'summary': 'UAE Dirham Symbol, New AED Currency Sign, Dirham Sign in Invoices, Reports, POS and Website, '
               'AED Symbol, UAE Currency Symbol, Emirati Dirham Sign',
    'description': """
UAE Dirham Symbol (AED)
=======================

A bridge until Odoo supports the sign.

The UAE Dirham sign (U+20C3) is new: it joined Unicode in version 18.0, and Odoo still shows 'AED' by
default.

This module displays the official sign today, using a small font for devices that don't support it yet.

Once Odoo supports the sign natively, we'll announce it here and discontinue this module.

Uninstalling the module restores 'AED', or Odoo's own sign if supported, without changing anything else in
your database.

Shows the new UAE Dirham sign (U+20C3, Unicode 18.0) instead of "AED" everywhere Odoo prints an
amount in dirhams: backend, PDF reports (invoices, quotations, payslips...), website, portal and
Point of Sale.

* Uses the official Unicode character, so copied amounts keep the real sign.
* A small web font draws the sign until operating systems ship it; nothing else changes:
  your interface fonts, report fonts and code editors keep their own fonts.
* Works with every report layout font (Lato, Roboto, Open Sans, Montserrat, Oswald, Raleway,
  Tajawal, Fira Mono), regular and bold.
* Symbol placed before the amount; uninstalling restores "AED" (or Odoo's own sign, once supported).

Contributor: Akshay Manoj.
""",
    'license': 'LGPL-3',
    'depends': ['web'],
    'data': [
        'views/res_currency_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_aed_currency_symbol/static/src/css/om_aed_symbol.css',
        ],
        'web.assets_frontend': [
            'om_aed_currency_symbol/static/src/css/om_aed_symbol.css',
        ],
        'web.report_assets_common': [
            'om_aed_currency_symbol/static/src/css/om_aed_symbol_report.css',
        ],
        'point_of_sale._assets_pos': [
            'om_aed_currency_symbol/static/src/css/om_aed_symbol_report.css',
        ],
    },
    'images': ['static/description/banner.png'],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
}
