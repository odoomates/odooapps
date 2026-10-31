==================================
Odoo 20 Automatic Currency Rates
==================================

This module updates the exchange rates of Odoo 20 Community Edition automatically from an online source,
daily, weekly or monthly, with a backup source for the currencies the main one does not quote.

Features
========

* Five rate sources are supported: Frankfurter and the European Central Bank, which need no key and
  quote about thirty major currencies; Open Exchange Rates, which quotes every currency and needs an
  App ID from openexchangerates.org; ExchangeRate-API, which works on its free feed without a key
  and uses your key when you enter one; and Central Bank, the official rates of a central bank.
* The Central Bank source reads, without key and without intermediary, the official rates published by
  the central bank itself, in the currency of its country (the mid rate when a bank publishes only
  buying and selling rates), for 36 countries; the euro area is covered by the European Central Bank:

  * Europe and Central Asia:

    * Armenia, Central Bank of Armenia: AMD rates of about forty currencies;
    * Belarus, National Bank of the Republic of Belarus: BYN rates of about thirty currencies, saved
      under the day they apply from;
    * Czech Republic, Czech National Bank: the CZK fixing of about thirty currencies, at 2:30 PM;
    * Denmark, Danmarks Nationalbank: DKK rates of about thirty currencies;
    * Georgia, National Bank of Georgia: GEL rates of about forty currencies, saved under the next day,
      the day they apply from;
    * Hungary, Magyar Nemzeti Bank: HUF rates of about thirty currencies;
    * Iceland, Central Bank of Iceland: the ISK official reference rates (mid rates) of 9 currencies;
    * Kazakhstan, National Bank of Kazakhstan: KZT rates of about fifty currencies;
    * Norway, Norges Bank: NOK rates of about forty currencies, around 4 PM Oslo time;
    * Poland, Narodowy Bank Polski: the PLN average rates of table A, about thirty currencies;
    * Romania, National Bank of Romania: RON reference rates of about 35 currencies;
    * Sweden, Sveriges Riksbank: SEK mid-market rates of about thirty currencies;
    * Switzerland, Swiss National Bank: CHF rates at 11 AM of EUR, USD, GBP and JPY;
    * Türkiye, Central Bank of the Republic of Türkiye: TRY indicative rates of about twenty currencies,
      set at 3:30 PM;
    * Ukraine, National Bank of Ukraine: UAH rates of about forty currencies, saved under the next
      working day, the day they apply from;
    * United Kingdom, Bank of England: GBP spot rates of 25 currencies, observed around 4 PM London
      time and published the next working day.

  * Middle East:

    * Bahrain, Central Bank of Bahrain: BHD rates of about thirty currencies;
    * Israel, Bank of Israel: ILS representative rates of 13 currencies, set around 3:30 PM;
    * Jordan, Central Bank of Jordan: JOD rates of USD, EUR, GBP, JPY and CHF;
    * Kuwait, Central Bank of Kuwait: KWD rates of about 120 currencies;
    * Oman, Central Bank of Oman: OMR rates of about 45 currencies;
    * Saudi Arabia, Saudi Central Bank (SAMA): SAR rates of about seventy currencies;
    * United Arab Emirates, Central Bank of the UAE: AED rates of about seventy-five currencies,
      published each working day around 6 PM UAE time.

  * Africa and South Asia:

    * Bangladesh, Bangladesh Bank: BDT rates of 11 currencies (the weighted average rate of the US
      dollar);
    * India, Reserve Bank of India: the INR reference rates computed by FBIL each working day around
      1:30 PM IST for USD, GBP, EUR, JPY, AED, IDR and RUB, read from the reference rate archive of the RBI;
    * Kenya, Central Bank of Kenya: KES indicative rates of about twenty currencies;
    * Nigeria, Central Bank of Nigeria: NGN central rates of 11 currencies;
    * Sri Lanka, Central Bank of Sri Lanka: LKR indicative rates of about fifty currencies.

  * Americas:

    * Argentina, Banco Central de la República Argentina: ARS closing rates of about 35 currencies;
    * Brazil, Banco Central do Brasil: the BRL PTAX closing rates of about 150 currencies, around
      1:10 PM Brasília time;
    * Canada, Bank of Canada: CAD daily rates of about 25 currencies, by 4:30 PM Eastern time;
    * Colombia, Banco de la República: the TRM of the US dollar, certified by the Superintendencia
      Financiera, read from the open data portal of the government, saved under the day it applies from.

  * Asia-Pacific:

    * Australia, Reserve Bank of Australia: AUD rates of about twenty currencies at 4 PM Sydney time;
    * Malaysia, Bank Negara Malaysia: MYR middle rates of about 25 currencies;
    * Philippines, Bangko Sentral ng Pilipinas: PHP reference rates of about thirty currencies;
    * Singapore, Monetary Authority of Singapore: SGD rates of 21 currencies, the average of the
      interbank buying and selling rates around noon.

  The bank is chosen in the settings, by default the bank of the country of the company. The rates are
  saved under the date the bank gives them, and named after the bank. Rates published with fewer than
  three significant digits (e.g. 0.0002 for a currency of very small unit) are left to the backup source.
* A second source can be set as backup: it gives the rates of the currencies the main source does not
  quote, and all of them when the main source fails.
* The rates are fetched against the base currency of the source and converted to the currency of the
  company, so any source can be used with any company currency.
* A scheduled action runs every day and updates the companies whose update is daily, weekly or monthly
  and whose next update date has come; companies left on Manually are never fetched.
* The update is done per company, so each company keeps its own source, keys, currencies and rates.
* Choose the currencies to update, or leave the list empty to update every active currency.
* The rates can be saved under the date given by the source or under the day of the update.
* A safety net holds back a rate that moves more than 20% (or the limit set in the settings, 0 to turn it
  off) from the latest rate of the currency: the other rates are saved, and the result of the update
  lists the currencies held back with the old and new values and the source, to be checked and entered
  by hand. The first rate of a currency is always saved.
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
Rates requires an App ID; ExchangeRate-API accepts an optional key; Central Bank needs the bank to read,
set from the country of the company when it has one. Optionally set a backup source, the
currencies to update, the date the rates are saved under, the change above which a rate is held back
(20% by default) and the date of the next update.

Missing the rate you are looking for? Let us know, we will be happy to add it: open an issue on
https://github.com/odoomates/odooapps/issues or write to odoomates@gmail.com.

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
