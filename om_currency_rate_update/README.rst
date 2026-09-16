==================================
Odoo 20 Automatic Currency Rates
==================================

This module updates the exchange rates of Odoo 20 Community Edition automatically from an online source,
daily, weekly or monthly, with a backup source for the currencies the main one does not quote.

Features
========

* Four rate sources are supported: Frankfurter and the European Central Bank, which need no key and
  quote about thirty major currencies; Open Exchange Rates, which quotes every currency and needs an
  App ID from openexchangerates.org; and ExchangeRate-API, which works on its free feed without a key
  and uses your key when you enter one.
* A second source can be set as backup: it gives the rates of the currencies the main source does not
  quote, and all of them when the main source fails.
* The rates are fetched against the base currency of the source and converted to the currency of the
  company, so any source can be used with any company currency.
* A scheduled action runs every day and updates the companies whose update is daily, weekly or monthly
  and whose next update date has come; companies left on Manually are never fetched.
* The update is done per company, so each company keeps its own source, keys, currencies and rates.
* Choose the currencies to update, or leave the list empty to update every active currency.
* The rates can be saved under the date given by the source or under the day of the update.
* A maximum change in percent can be set: a rate that moves more than that from the previous one is not
  saved and is reported in the result of the update.
* Updating twice on the same day replaces the rate of that day instead of adding a second one.
* Each rate keeps the name of the source it came from, shown in a Source column of the rate list; the
  column is emptied when the rate is changed by hand.
* The date, result and messages of the last update are shown in the settings, including the currencies
  no source quoted and the errors returned by the sources.
* After three failed updates in a row, the accounting advisers of the company are notified.
* A Test Connection button fetches the rates without saving them and shows a sample of what the source
  returns; an Update Now button fetches and saves them immediately.
* The API keys are stored on the company and are only readable by the settings administrators; they are
  hidden from the error messages returned by the sources.
* A failure on one company does not stop the update of the other companies.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

Upgrade
============

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.


Configuration
=============

Multi-currency must be enabled in Accounting > Configuration > Settings; the Automatic Currency Rates
setting appears in the same place.

Set how often the rates are updated (Manually, Daily, Weekly or Monthly) and the source. Open Exchange
Rates requires an App ID; ExchangeRate-API accepts an optional key. Optionally set a backup source, the
currencies to update, the date the rates are saved under, the maximum accepted change and the date of
the next update.

Usage
=====

Click Test Connection to check the source, then Update Now to fetch the rates at once. Once an interval
other than Manually is set, the scheduled action "Accounting: update the currency rates" keeps them up
to date. The rates and the source they came from are listed on each currency, under
Accounting > Configuration > Accounting > Currencies.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
