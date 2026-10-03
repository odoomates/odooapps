===================
User Access Manager
===================

.. note::

   **Beta.** Reviews and feedback are welcome. Every feature is covered by
   automated tests, but access rules touch every screen of Odoo: build and
   check your profiles on a copy of your database first, with *Test as User*,
   before you give them to your users. Report what you find at
   odoomates@gmail.com or on GitHub.

Group users into access profiles and decide, from a single screen, which menus
they see, which models they may read, create, edit and delete, which buttons
they may press, which fields are hidden or read-only, which reports they may
print, and whether the chatter is shown.

A user who carries no profile is not restricted in any way: the module does
nothing until you put someone in a profile.

Features
========

* Access profiles, assignable to any number of users. A user may carry several.
* Set the profiles of many users at once from the Users list (*Action > Set
  Access Profiles*: add, remove or replace), and mark a profile *Give to New
  Users* so every new internal user gets it. The users list shows the profiles,
  with filters and a group by.
* An optional company per profile: set it and the profile only applies to the
  users who have that company.
* Two ways of combining, chosen per profile:

  * **Additive** profiles combine permissively with the other additive profiles
    of the same user: an operation is allowed as soon as one of them allows it,
    and something is hidden only when all of them hide it. This is how Odoo
    groups already behave.
  * **Override** profiles always apply and can never be overruled, which is
    what a blanket such as "Read Only" stacked on top of another profile needs.

* **Ready-made profiles**: *New from Template* offers a salesperson, sales read
  only, an accountant without configuration, an auditor, a warehouse operator, a
  purchase user, a cashier, an HR officer without salaries, and for any app a
  user without configuration or a read only user. Only the templates of the
  apps installed are offered, and the profile created is an ordinary one.
* **Restrict an App**: pick an app and see, on one screen, its menus, its data
  (read, create, edit, delete, and their own records only), its reports and the
  entries of its Action menu, each with a checkbox. An access level (full, user
  without configuration, read only, no access) ticks them for you. Data the app
  shares with other apps, such as customers, is marked and never changed by a
  level.
* Hide menus and whole apps on the real menu tree: untick a menu to hide it
  with everything below it, search a menu by its name, and see per app how many
  menus are hidden.
* Read, edit, create and delete rights per model, enforced on the server, so
  the Create and Delete buttons disappear from the screen on their own.
* **Allowed Records**: only these journals, points of sale, warehouses,
  locations, sales teams or dashboards, and only what belongs to them (allowing two journals
  also filters their entries, journal items and payments). Pick them by name on
  the profile, or tick *Each User's Own* and set them on each user's form, so
  one profile serves every cashier, each on their own point of sale. A kind is
  offered only when its app is installed.
* **Hide Costs and Margins** and **Hide Sales Prices**: one switch each, for the
  product cost, the margins of sales and of the point of sale and the stock
  valuation, or for the sales prices, discounts and amounts, in every app
  installed now or later.
* Hide the whole **Print** menu or the whole **Action** menu, everywhere or for
  one model: the reports cannot be printed and the actions cannot be run either.
* Hide parts of the **chatter**: *Send message* (only *Log note* remains, and
  sending is refused on the server too), the followers, the attachments.
* A **home page** per profile: where its users land after signing in.
* **Sign-in rules**: working hours per day (in the timezone of the profile),
  allowed networks (addresses or ranges), and one session per user (signing in
  ends the user's other sessions). Checked at sign-in and on every request: a
  session ends when the working hours are over or when it is used from a
  network that is not allowed.
* **History**: every change of a profile, of its switches and of its lines
  (data rules, fields, buttons, view elements, allowed records) is logged in
  its chatter, with who made it and when.
* **Effective access on the user form**: what the user really ends up with, all
  of their profiles combined.
* **Export and import** of profiles as a file, to build them on a test database
  and load them on production. Menus, reports, actions and allowed records are
  matched by external id, else by name; what the other database lacks is
  skipped and listed in the chatter of the profile. Users are matched by login,
  if asked.
* A refusal caused by a profile says so plainly, instead of Odoo's generic
  message, without naming the records refused.
* Record filters in one click: *their own records*, *their sales team*, *their
  companies*, *their warehouse*, *edit drafts only*, each offered only when the
  data has what it needs, and Odoo's filter editor for anything else.
* Record filters per model, evaluated like a standard access domain with
  ``user``, ``company_id`` and ``company_ids``. One filter applies to all four
  operations, and each operation can be narrowed further on its own: that is
  how you allow editing only draft records without hiding the others.
* Hide buttons, block them on the server, or both. A scan reads the buttons out
  of the views of a model so you pick them from a list; stat buttons and action
  buttons are covered.
* Hide fields, force them read-only or required, remove the external link of a
  relational field, stop creating records from its dropdown, and filter the
  values it offers.
* Hide notebook tabs, search filters and group-bys, the search panel, and whole
  view types such as Kanban.
* Hide reports and the entries of the Action menu (server actions and window
  actions such as Send by Email). They leave the Print and Action menus, and are
  refused when reached by their id or by their report URL.
* Hide the chatter, for the whole system or for one model.
* Block export, import, archiving and duplication on the server, and lock
  clickable status bars.
* Block the login of the users of a profile: every sign-in is refused, in the
  browser and through the external API, and their open sessions end at once.
  Their records stay untouched, and taking them out of the profile lets them
  back in, e.g. at the end of a leave.
* Block developer mode, and refuse XML-RPC and JSON-RPC sign-ins for the users
  of a profile while leaving the browser working.
* An **Effective Access** wizard showing what a given user really ends up with
  and which profile produced each line.
* A **Copy Restrictions** wizard, because under a permissive union a restriction
  only bites when every additive profile of the user carries it.

Installation
============

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

Upgrade
=======

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.

Configuration
=============

There is nothing to configure. Go to Settings > Users & Companies > Access
Profiles and create a profile.

Usage
=====

Create a profile, add the users to it, then fill the tabs you need:

* **Switches** for the settings that apply to the whole system.
* **Menus & Apps** for the menus to hide.
* **Models** for the rights per model. The *Load Models* button fills the tab
  with the models reachable through the menus the profile still shows.
* **Buttons** for the buttons to hide or block. The *Scan Buttons* button reads
  them out of the views of a model and lets you tick the ones to restrict.
* **Fields** for the fields to hide or lock.
* **Reports & Actions** for the reports and server actions to hide.

Use *Test as User* on the profile, or Settings > Users & Companies > Effective
Access, to see what a user really ends up with before you rely on it.

Limits
======

Read this before you use the module to protect anything that matters.

* **Hidden is not blocked.** Menus and view nodes that are hidden are cosmetic:
  the record is still reachable by its URL. Only the rights of the Models tab
  and the blocking mode of the Buttons tab refuse anything on the server. This
  is why the default mode of a button rule is *Hide and block*.
* **Hidden and read-only fields are enforced at the boundary, not inside
  Odoo.** What a user, the browser console or a script asks for (web client,
  JSON-2, XML-RPC and JSON-RPC) never carries a hidden value: it is stripped
  from what is read, and filtering, sorting, grouping or exporting on it is
  refused; what is written to a read-only or hidden field is ignored. Odoo's own
  code still reads and writes these fields as the user, on purpose: hiding the
  product cost must not stop a delivery from being validated. A report or a
  document Odoo builds itself (a PDF, an email) may therefore still show the
  value: hide that report too.
* **A blocked button is refused from the web client and the JSON-2 API**,
  clicked or called by hand. Scripts using the older XML-RPC or JSON-RPC are not
  covered: tick *Block the External API* on the same profile.
* **A company on a profile follows the users, not the company switcher.** The
  profile applies to everyone who has that company among theirs, whichever
  company they are working in. It cannot follow the switcher: core caches the
  menus per user with no company in the key, so a profile that changed with the
  active company would leave stale menus on screen.
* **A field's value filter is a convenience, not a guarantee.** It narrows the
  dropdown; it does not refuse a value that arrives by other means. When two
  profiles set one on the same field they are combined only if both are plain
  literals, otherwise the first is kept.
* **A hidden view type is dropped from the action, not forbidden.** The last
  remaining view type of an action is always kept, so an action can never end
  up with nothing to render.
* **Blocking the external API blocks signing in, not the protocol.** A session
  already open, or a user without the flag, is unaffected.
* **A hidden field stays in the screens, invisible**, with a blank value:
  other parts of a view may refer to it (a total, a condition), and fail when
  it is gone. It is removed from search, graph and pivot views, together with
  the search filters and group-bys using it.
* **Hiding Send message only covers the chatter.** Sending by email from a
  document (*Send by Email*, a mail template) is a business flow and stays
  available: hide that action or its button too where it matters. Hiding the
  followers and the attachments is cosmetic.
* **Hiding the Print menu refuses every report of the model**, including one an
  email would attach.
* **Allowed networks need the real address.** Behind a reverse proxy (nginx,
  a load balancer), start Odoo with ``--proxy-mode``, or every request comes
  from the proxy's address.
* **Blocking a button ignores the view and the button id.** The server only
  learns which model and which method were called, so a rule that blocks a
  method blocks every button calling it.
* **XML-RPC and JSON-RPC and the allowed networks.** Odoo knows the address of
  these old protocols only when it serves them for a database (a single
  database, or a database filter). Otherwise the address is unknown, and a
  profile with allowed networks refuses the sign-in rather than let it through.
  The JSON-2 API (API keys) is always checked.
* **Record filters read the user when they are built.** A filter on a value of
  the user other than their companies and their default warehouse (their
  employee, their sales team field) follows a change of that value only after
  the next change of a profile.
* **The last-administrator guard looks at one profile at a time**, and counts on
  the Administrator user staying active: two profiles together, or an archived
  Administrator, are not caught.
* **A permissive union only ever widens.** Adding an additive profile to a user
  can only give access back, never take it away. Use an override profile, or
  copy the restrictions into every profile the user carries.
* **The superuser and the Administrator user are never restricted**, whatever
  the profiles say. A member of the Settings group is only restricted by a
  profile that ticks *Apply to Settings Users*. This is deliberate: without it,
  a profile could leave the database with no way back in.
* Denying read on a model the interface needs will break the session of the
  users in that profile. Remove the profile from them to recover.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>

Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
