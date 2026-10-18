==============================
Hide Menus by User and Company
==============================

This module hides any menu or app of Odoo 20 for a user, or for every user while a company is the
current company.

Features
========

* Hide a menu for a user, in every company, from the Hidden Menus tab of the user.
* Hide a menu for everyone while a company is the current company, from the Hidden Menus tab of the
  company. Switching to another company in the company switcher shows the menus of that company.
* Hiding a menu hides its sub-menus. A folder left with nothing to open is hidden too, and an app
  whose first menu is hidden opens the next one.
* The Hidden For tab of a menu shows and changes the same rules, from the side of the menu.
* Settings > Users & Companies > Hidden Menus lists every hidden menu with its users and companies.
* The rules apply to the administrators as well, but they always keep the Settings app, so that no
  rule can lock them out of it.

Hiding a menu is not an access right: a user who knows the address of a page can still open it. Use
the groups and record rules of Odoo to forbid the data itself.

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

There is nothing to configure. Only the users of the Settings group see and change the hidden menus.

Usage
=====

Open a user in Settings > Users & Companies > Users, go to the Hidden Menus tab, add the menus to hide
and save. To hide menus in a company, do the same in the Hidden Menus tab of the company. The user sees
the change on the next page load.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
