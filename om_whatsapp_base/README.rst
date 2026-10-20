=======================
WhatsApp Connector Base
=======================

This module adds WhatsApp templates, a composer and a log of every WhatsApp message to Odoo 20. It
sends with Click to Chat out of the box, and is the base of the other Odoo Mates WhatsApp modules,
which add other ways to send and receive.

Features
========

* Send a WhatsApp message from a contact, or from any document with a template, through the Action
  menu. The number is found on the document or on its customer.
* Templates per kind of document, filled with its values: ``Hello {{ object.partner_id.name }}``.
  A template can also print a report and send it as a PDF, with the providers that send files.
* Send to several documents at once, with the template filled in for each of them, with the
  providers that send in batch. Numbers of the phone blacklist and documents without a valid number
  are skipped.
* Every message is a message of the chatter of its document, with the WhatsApp icon and its status
  (queued, sent, delivered, read, failed), and is listed in WhatsApp > Messages. A failed message
  is in the failures of the messaging menu, and is sent again from its status.
* WhatsApp conversations in Discuss, one per number, shared by the users of the account: a WhatsApp
  tab in the messaging menu and in Discuss, the chat window opens on a new message, and what a user
  writes there goes out on WhatsApp. The messages sent from documents are in the conversation too,
  with their ticks, and its header opens the document it last spoke about.
* Received messages go to the conversation, and to the chatter of the document they answer: the one
  of the message they quote, else the one of the last message sent to that number within the reply
  window of the account, and as an answer to the message they quote. The followers get them in their
  Inbox, never by email. Voice messages play in Odoo, and the reactions show on the messages.
* Profile pictures (option Profile Pictures on the account, on by default): a customer without a photo
  in Odoo gets their WhatsApp profile picture as the photo of their contact, once; an unknown number
  shows it on its conversation, refreshed weekly, and gives it to the contact made from it. A photo set
  in Odoo is never replaced. With the providers that can (WhatsApp Web, WhatsApp QR), as the privacy
  settings of the customer allow.
* Replies: a message answered in Discuss (Reply) goes as a quoted reply in WhatsApp, with the providers
  that can (Meta, WhatsApp QR; WhatsApp Web as far as WhatsApp Web allows it).
* Read and played receipts: a user of the account who reads a WhatsApp conversation in Discuss marks
  the messages of the contact read in WhatsApp (blue ticks), and a voice message played in Odoo is
  marked played, with the providers that can (WhatsApp Web, WhatsApp QR; Meta marks read only). The
  privacy settings of the phone still apply.
* Reactions both ways: a user of the account who reacts to a WhatsApp message in Odoo (Discuss or the
  chatter) reacts in WhatsApp too, with the providers that can (WhatsApp Web, Meta, WhatsApp QR). One
  reaction per person, as in WhatsApp: a new one replaces the one before; taking it back takes it back
  there.
* A number Odoo does not know, neither a contact nor a chat about a document, opens a conversation
  named by its number and WhatsApp name, where Create Contact makes the contact with its number. With
  Keep Chats of Unknown Numbers unchecked on the account, its messages are not kept.
* Saved replies (canned responses) in the conversations: type ``::``.
* Send WhatsApp from automation rules, contextual actions and scheduled actions: a server action of
  type Send WhatsApp sends a template, with its report as a PDF, for example when an order is
  confirmed. Providers that send from the server send every record; WhatsApp Web sends one message
  triggered by a user of the account from their browser, and fails the others with the reason, to be
  sent again from the chatter. Sending never stops the flow that triggers it.
* Accounts: each WhatsApp number has its allowed users, who send from it.

Click to Chat opens the chat in a new tab with the text filled in, and the user presses send in
WhatsApp. It sends one message at a time, without files, and Odoo cannot know whether it was
delivered.

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

Go to WhatsApp > Configuration > Accounts, create an account and add its allowed users. Give the
users the WhatsApp User access in their settings; the WhatsApp Administrator manages accounts and
templates and sees every message.

Usage
=====

Open a contact and use Action > Send WhatsApp. To send from other documents, create a template in
WhatsApp > Templates and click Add Action Menu: the template is then in the Action menu of that kind
of document.

To send automatically, for example the quotation when an order is confirmed, set up an automation
rule yourself (the WhatsApp modules do not install the Automation Rules app):

1. In Apps, install Automation Rules (``base_automation``).
2. In developer mode, open Settings > Technical > Automation Rules and create a rule on Sales Order,
   with the trigger State is set to Sales Order.
3. Add an action of type Send WhatsApp, choose the template (its report goes as a PDF) and, if needed,
   the account to send from.

The same works on invoices, deliveries and any document with a chatter.

Providers
=========

A WhatsApp message is a ``mail.message`` of type ``om_whatsapp``; a sent one has a
``mail.notification`` of type ``om_whatsapp`` per recipient, which holds its status with the values
of Odoo: ``ready`` (queued), ``pending`` (sent), ``sent`` (delivered), ``is_read`` (read),
``exception`` (failed) and ``canceled``.

A provider module adds its key to the ``provider`` field of ``om.whatsapp.account`` and implements
``_om_whatsapp_send_<key>(notifications)``. It moves the notifications with
``_om_whatsapp_set_status()``, records what comes in with ``account._om_whatsapp_receive()`` and
``account._om_whatsapp_update_status()``, and extends ``_compute_capabilities`` when it sends files
or batches.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
