{
    'name': 'Odoo 20 Automatic Currency Rates',
    'version': '1.1.0',
    'category': 'Accounting',
    'summary': 'Update the exchange rates automatically from the European Central Bank, Frankfurter, '
               'Open Exchange Rates, ExchangeRate-API or the official rates of 36 central banks',
    'description': """
Update the currency rates of each company automatically, daily, weekly or monthly, from the source of your choice:
European Central Bank, Frankfurter, Open Exchange Rates (every currency, with an App ID), ExchangeRate-API or the
official rates of a central bank (36 countries, among them the United Kingdom, Switzerland, the Nordics, India, Saudi
Arabia, the UAE, Türkiye, Poland, Brazil, Canada, Australia and Singapore), with a backup source for the currencies the
main one does not quote.
    """,
    'sequence': '1',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': ['account', 'mail'],
    'data': [
        'data/ir_cron.xml',
        'views/res_config_settings_views.xml',
        'views/res_currency_views.xml',
    ],
    'images': ['static/description/banner.gif'],
}
