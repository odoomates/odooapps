=========
Approvals
=========

Approval flows for any app: put a button of any model under approval, e.g.
Confirm on the sale orders above 10,000, and it waits for its approvals before
it runs. Other modules use the same flows to approve their own documents, such
as the HR requests and the loans.

Features
========

* An approval flow per button of any model, chosen from the buttons of its form
  and list views, without any development.
* The Approval Designer: a flow is a chain of cards, from the button stopped to
  the button running, with its steps in between. Click a card to edit it on
  the side: the button among the buttons of the model, the records it applies
  to (with one-click conditions such as Total above), who approves each step
  (people, a group, or a person on the record chosen field by field, e.g.
  Sales Team > Team Leader), when a step applies, reminders and escalation.
  Insert a step with +, move it up or down. Each change describes the flow
  again in words below the chain, and the cards say what is missing; a flow
  with something missing cannot be activated.
* New opens a gallery: approval above an amount, two-level approval, approval
  by the person responsible, approval of a discount, approval to cancel, or
  blank. The templates come ready for quotations, purchase orders, vendor
  bills and transfers when their apps are installed, and guess the button, the
  amount and the person responsible of the other records. A flow made from the
  gallery or the designer starts inactive.
* Set up an approval, in the gear menu of any form, opens the gallery for that
  kind of record, for the approval managers.
* Demo data: with demo data, the templates of Sales, Purchase, Invoicing and
  Inventory are added as inactive flows for the apps installed, also when an
  app is installed later; each app gets them once, so deleted ones stay
  deleted. Activate one to try it.
* A flow applies to the records matching its domain and above an amount, and
  to one company or all of them. The first matching flow is used.
* Amounts in a currency: the flow compares an amount of the record, e.g. the
  total of a sale order, with its threshold in the currency of the flow; an
  amount in another currency is converted first. A step can apply only above a
  higher amount, e.g. the director above 20,000.
* Steps approved in turn, by given users, by the users of a group, or by the
  user a field of the record names, e.g. ``user_id`` for the salesperson. A
  step can apply only to some records.
* Who must approve a step: any one of its approvers, all of them, or a number
  of them, e.g. two directors of three. A refusal by any of them refuses the
  step; an approval manager decides for the whole step. The record shows how
  many approved so far.
* Notes, set per flow as not asked, optional or required: the requester's note
  when clicking the button, with files, the approver's note when approving,
  and when refusing. The approvers read the requester's note and open the files
  on the record.
* A step finding nobody is approved by the fallback group of the flow, by
  default the approval administrators.
* The requester may approve their own steps, or leave them to somebody else.
* Clicking the button asks for the approval and tells the user who it waits
  for, with the message of the flow. Once approved, the button runs as the
  requester, or the requester clicks it again.
* Each approver gets an Approval activity; the record and the requester are
  told of the decisions.
* A refusal shows at the top of the record, with who refused and why, until
  the requester dismisses it or asks again.
* Clicked for several records, the button runs only once all of them may run:
  the approvals already given are kept for the next click.
* The record is locked from the request on: read-only in its form and refused
  by the server, for its lines too when they are saved with it, so nothing
  changes between the request and the button running. A flow can leave the
  record editable instead. Once approved, the record unlocks when the button
  has run, or, as the flow chooses, stays locked until an approval manager
  unlocks it. A refusal or a withdrawal unlocks it.
* A banner at the top of the form says what the record waits for, which step
  and who approves it, with Approve and Refuse for the approvers, Withdraw for
  the requester, Unlock for the approval managers, and the steps in Details.
* Each flow says in a few lines what it does, and Test on a Record shows, for a
  record and a requester, whether the flow applies, which steps are skipped,
  who would approve, and whether the record would be locked, without asking
  anything.
* Approvals > To Approve lists what waits for you, from every app; My Requests
  follows the approvals you asked for; All Requests shows them all to the
  approval administrators.
* Delegations: an approver away names a substitute for a period, for every
  flow or some of them (Approvals > My Delegations); the approval
  administrators delegate for anyone. The substitute is asked the steps waiting
  for the approver, decides "on behalf of" them, and the approver still can:
  the first decision counts. The substitute of a substitute is followed too;
  the requester never stands in for their own request unless the flow lets
  them approve it.
* A substitute set in the preferences of each user, suggested on their
  delegations.
* Reminders and escalation per step: the approvers are reminded after some
  days, then other users are asked to decide too: given users, a group, or the
  fallback group of the flow.
* For developers: a model inheriting ``approval.mixin`` gets an approval of
  its own, submitted, approved, refused, cancelled or set back to draft.

Configuration
=============

* Give the Administrator access of Approvals to the people who set up the
  flows; they can also approve any step.
* Create the flows in Approvals > Configuration > Approval Flows: New starts
  from a template, a flow opens in the Approval Designer. Set the button, the
  records it applies to, the steps, the message shown to the requester and
  whether the record is locked; on the last card, whether the button runs by
  itself and whether the record stays locked once approved. Check the flow
  with Test on a Record, then activate it. The usual form stays available
  (Form View in the designer).

Usage
=====

* Click a button under approval: a notification says the approval is asked.
* The approvers open Approvals > To Approve and approve or refuse.
* Approval rules stop the buttons clicked in the web client and the same
  methods called through the web client's RPC, and the external APIs too:
  JSON-2, XML-RPC and JSON-RPC answer that the approval is asked instead of
  running the button. A flow requiring the requester's note cannot be asked
  through an API: the call fails, telling to ask in Odoo. Server code calling
  the method directly is not stopped.
* The lock refuses the changes of the users, whatever the way; the chatter,
  the activities and the followers of a locked record still work, and code
  running as the super user is not stopped. Archiving a flow, or switching its
  lock off, unlocks the records it locked. Developers list more fields a
  locked record still lets change in ``_approval_lock_exempt_fields``.

Editions
========

Works with Odoo 20 Community and Odoo 20 Enterprise. On Enterprise, it cannot
be installed together with the Enterprise Approvals app (``approvals``): both define
the same records. Use one or the other.

Dependencies
============

* Base (``base``), Discuss (``mail``), Web (``web``) and the RPC endpoints of Odoo
  (``rpc``), all installed with Odoo by default

Support
=======

Odoo Mates, odoomates@gmail.com
