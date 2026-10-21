======================
WhatsApp Connector Web
======================

This module sends WhatsApp messages and PDFs from Odoo 18 through WhatsApp Web, open in another tab
of the same browser, with the Odoo Mates WhatsApp Connector browser extension for Chrome and Firefox,
and brings the replies back to Odoo. No WhatsApp Business API account is needed, and the user stays
on the Odoo page.

Features
========

* A WhatsApp Web provider for the accounts of WhatsApp Connector Base (``om_whatsapp_base``).
* Send from a contact, or from any document with a template, with its files and the PDF of the
  report of the template. The extension opens the chat in the WhatsApp Web tab, sends the text and
  the files, and tells Odoo whether it worked.
* The message is logged as sent, or failed with the reason, and can be sent again from its status
  on the chatter. Its ticks follow WhatsApp: delivered, then read.
* Receive: while WhatsApp Web is open, the extension (1.1.0 or later) reads its messages, and the open
  Odoo pages of the user record them: the replies go to the chatter of the document they answer, with
  their pictures, documents, stickers and voice messages, and the messages typed on the phone and the
  reactions are logged too. A number Odoo does not know opens a conversation where the contact is
  made in one click; with Keep Chats of Unknown Numbers unchecked on the account, only its contacts and
  the chats about its documents are kept, and the messages of the other numbers never leave the
  browser. Groups, status and channels are not read.
* While WhatsApp Web is closed or not synced, what it read waits in the extension (1.5.2 or later): the
  messages come to Odoo together, in order and with their files, once it is open again.
* Profile pictures are read in WhatsApp Web (extension 1.7.0 or later), a few every five minutes.
* Read and played receipts go through the browser of the user (extension 1.6.0 or later).
* Connection status (extension 1.5.0 or later): a green or red dot shows whether WhatsApp Web is open
  and linked in this browser, with the number of the account, in the top bar, on the account (with
  why and Open WhatsApp Web) and in the list of the accounts. The account keeps when it was last
  connected, and by whom. The composer and the WhatsApp conversations warn when a message would not
  go from this browser.
* A reaction made in Odoo goes through the browser of the user who made it (extension 1.4.0 or later),
  to a message WhatsApp Web has; otherwise the user is told why.
* The WhatsApp linked in the browser must be the number of the account (or the account has no
  number and is the only WhatsApp Web account of the user): another WhatsApp is never read into it.
* Without the extension, or in an Odoo address the extension does not allow, Send opens a dialog: click
  the icon of the extension and Allow this Odoo, then Send again; or open the chat in WhatsApp Web with
  the text filled in, without the files.

It sends one message at a time, each one started by the user: WhatsApp does not allow automated or
bulk sending from WhatsApp Web, and may ban the numbers that do.

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

* Install the Odoo Mates WhatsApp Connector extension in Chrome or Firefox. On a page of your Odoo,
  click its icon and Allow this Odoo (or add the address in its options).
* Open web.whatsapp.com once and link it to your phone.
* In WhatsApp > Configuration > Accounts, set the provider of the account to WhatsApp Web.

Usage
=====

Send a WhatsApp message as with the base module. The WhatsApp Web tab may stay in the background; it
is opened, pinned, when it is not open.

To send the quotation when an order is confirmed, set up the automation rule of the base module (see
its README; install the Automation Rules app first), with this account on its Send WhatsApp action.
The message goes when a user of the account confirms one order from their browser; orders confirmed
several at once or without a user (website, import) fail with the reason, to be sent again from the
chatter.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
