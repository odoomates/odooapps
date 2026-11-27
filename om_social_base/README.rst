============
Social Inbox
============

This module brings the chats of your customers into Odoo 20, in one inbox in Discuss. It is the
base of the Odoo Mates messaging channels: a channel module (WhatsApp Connector Base) brings its
accounts and how messages travel, the Social Inbox keeps the conversations, the messages and their
status.

Features
========

* Accounts: a number or a handle of a channel, its provider, the users who answer from it, the reply
  window, whether it keeps the chats of unknown customers and shows their profile pictures.
* Conversations in Discuss, one per customer and account, shared by the users of the account: a
  Social Inbox tab in the messaging menu and in Discuss, the chat window opens on a new message, and
  what a user writes there goes out on the channel. The header opens the document the conversation
  last spoke about.
* Received messages go to the conversation, and to the chatter of the document they answer: the one
  of the message they quote, else the one of the last message sent to that customer within the reply
  window, as an answer to the message they quote. The followers get them in their Inbox, never by
  email.
* The status of every message sent (queued, sent, delivered, read, failed, cancelled), with ticks in
  the chatter and in Discuss. A failed message is in the failures of the messaging menu, and goes
  again from its status. Social Inbox > Messages lists every message, with filters.
* Read and played receipts, reactions both ways, quoted replies, voice messages, with the providers
  that can.
* Customer identities: the address, user ID, username and profile name a channel gives a customer,
  linked to their contact. A customer whose number is not shared is still found by their user ID.
* An unknown customer opens a conversation named by their address and profile name, where Create
  Contact makes their contact; the conversation and its messages move to it.
* Profile pictures of the customers without a photo in Odoo, with the providers that can read them.
* A composer (``om.social.composer``) that channel modules extend.

Configuration
=============

#. Install a channel module, e.g. WhatsApp Connector Base, and one of its providers.
#. Go to Social Inbox > Configuration > Accounts and create an account: its channel, provider,
   address and allowed users.
#. Give your users the Social Inbox access rights (User, or Administrator to manage the accounts).

For developers
==============

* A channel module adds its key to ``om.social.account.channel`` and may extend
  ``_om_social_format_address``, ``_om_social_clean_address``, ``_om_social_is_user_ref`` and
  ``_om_social_find_partner_by_address``, and register the icon and name of the channel in the
  JavaScript registry ``om_social_channels``.
* A provider module adds its key to ``om.social.account.provider`` and implements
  ``_om_social_send_<provider>(notifications)``; optionally ``_om_social_react_<provider>``,
  ``_om_social_receipt_<provider>`` and ``_om_social_picture_<provider>``, and extends
  ``_compute_capabilities`` (files, batches, sending without a user) and
  ``_om_social_free_text_until`` (a window for free text).
* Incoming data goes to ``_om_social_receive``, ``_om_social_update_status`` and
  ``_om_social_receive_reaction`` of the account; a message is posted from code with
  ``_message_om_social`` on any document with a chatter.
* A message of the Social Inbox is a ``mail.message`` of type ``om_social``; a sent one has an
  ``om_social`` notification per recipient, which holds its status.

Bug Tracker
===========

Bugs are tracked on GitHub Issues. In case of trouble, please check there if your issue has already
been reported.

Credits
=======

Authors
-------

* Odoo Mates

Maintainers
-----------

This module is maintained by Odoo Mates.
