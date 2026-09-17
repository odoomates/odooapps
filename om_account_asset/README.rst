=========================
Odoo 20 Assets Management
=========================

This module adds fixed asset and revenue recognition management to Odoo 20
Community Edition. Each asset keeps a depreciation board of journal entries that
the module maintains through the whole life of the asset.

Features
========

* Record an asset with its gross value, salvage value, acquisition date and
  asset type, and follow its residual value and book value on the form.
* Group the settings of similar assets in an asset type holding the asset
  account, the accumulated depreciation account, the expense account, the
  journal and the depreciation method.
* Compute the depreciation with the linear, degressive, or degressive then
  linear method, over a number of entries, up to an ending date, or at a yearly
  depreciation rate.
* Start the depreciation on the purchase date with prorata temporis, on the last
  day of the purchase period, or on a first depreciation date you type.
* Enter the depreciation already booked elsewhere in the Opening Depreciation
  field: it is deducted from the first entries and no journal entry is created
  for it.
* Preview the depreciation board on a draft asset, then confirm the asset so
  that the past entries are posted and the later ones are posted on their date.
* Create the assets of a vendor bill automatically: a bill line with an asset
  type creates its asset when the bill is posted, and the type can confirm the
  asset at once or create one asset per unit of the line.
* Let an asset type claim the vendor bill lines booked on its asset account, so
  the lines get their type without the encoder choosing it. The Asset Category
  column of the bill lines is hidden by default: show it from the optional
  columns when a category has to be chosen by hand.
* Open the assets of a vendor bill, and the assets of an asset category, from a
  smart button on the bill and on the category.
* Set an Asset Type and a Deferred Revenue Type on a product so that bill and
  invoice lines are filled in from the product.
* Modify a running asset from a date: the running period is depreciated first, a
  lower value books a re-evaluation entry and a higher value creates a linked
  value increase asset.
* Pause a running asset and resume it later; the paused time is added to the
  life of the asset and the value increases follow it.
* Sell or dispose of the whole asset or of a share of it, booking the gain or
  the loss on the accounts set in the accounting settings and linking the sale
  to the customer invoice lines.
* Cancel an asset to remove it from the books: its entries are deleted, or
  reversed when they cannot be deleted, and the chatter records what happened.
* Protect the board: entries of a running asset cannot be deleted outside the
  asset actions, and changing the depreciation of a draft entry spreads the
  difference over the following ones.
* Print the Depreciation Schedule for a period: an asset register and a
  statement of the movements of cost, accumulated depreciation and net book
  value per asset type. An Excel version is offered when the Accounting Excel
  Reports module is installed.
* Analyse the depreciations in the graph and pivot views of the Assets Analysis
  report.
* Access rights per group: accounting managers get full access on assets and
  asset types, invoicing users can create assets, and auditors can read the
  analysis report. Multi-company rules limit assets and asset types to the
  companies of the user.

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

Create your asset types in Accounting > Configuration > Accounting > Asset
Categories (Configuration > Management when Odoo 20 Accounting
(om_account_accountant) is installed), with their accounts, journal and
depreciation method.

Set the gain and loss accounts used when an asset is sold or disposed of in
Accounting > Configuration > Settings, under Asset gains and losses.

Optionally set the Asset Type and the Deferred Revenue Type of your products on
the Accounting tab of the product form.


Usage
=====

Go to Accounting > Accounting > Assets and create an asset, or let a
posted vendor bill create it. Check the board with Compute Depreciation, then
press Confirm to start the depreciation.

On a running asset, use Modify Depreciation, Pause, Resume Depreciation, Sell /
Dispose or Cancel as the life of the asset requires.

Print the schedule from Accounting > Reporting > Management > Depreciation
Schedule, and open the analysis from Accounting > Reporting > Management >
Asset Analysis.


Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
