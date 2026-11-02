===========================
Leases: Right-of-use Assets
===========================

This module links the leases of Loans and Leases (om_account_loan) with Assets
Management (om_account_asset) in Odoo 20 Community Edition: the right-of-use
asset of a lease is created on its recognition and depreciated over the lease
term. It is installed automatically when both modules are installed.

Features
========

* A Right-of-use Asset Category on the lease (an asset category of the
  company). The initial recognition of the lease debits the asset account of
  the category: Dr Right-of-use asset / Cr Long-term lease liability, at the
  present value of the lease payments.
* The right-of-use asset is created at the same time: its gross value is the
  lease liability (in the company currency, at the rate of the start date),
  from the start of the lease, depreciated linearly, prorata temporis, to the
  end of the lease term (the last due date, or one period after it for a lease
  paid in advance), with the journal, the accounts and the period of the
  category. It is confirmed when the category confirms its assets
  (Auto-Confirm Assets), else left in draft to check.
* The asset shows on the lease (Right of Use button); cancelling the
  recognition of the lease cancels it (a draft asset is deleted).

For example, a lease of 12 monthly payments of 1,000.00 at 6% from
1 January 2025 is recognized at 11,618.93: its asset in a monthly category
depreciates 968.24 at the end of each month of 2025.

Without a category, the lease debits its Right-of-use Asset Account and no
asset is created.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. It is installed with Loans and
Leases and Assets Management; install it if they are already installed.

Upgrade
=======

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.

Configuration
=============

Create an asset category for the rights of use (Accounting > Configuration >
Asset Categories), with the right-of-use asset account, its accumulated
depreciation and depreciation expense accounts, the journal and the period of
the depreciations.

Usage
=====

On the lease, in the Accounting tab, choose the Right-of-use Asset Category,
then confirm the lease.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>

Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
