===================
User Access Manager
===================

.. note::

   **Completely free, and open source (LGPL-3).** Reviews and feedback are
   welcome: tell us what works, what does not and what you miss, at
   odoomates@gmail.com or on GitHub. Every feature is covered by automated
   tests; access rules touch every screen of Odoo, so build and check your
   profiles on a copy of your database first, with *Preview as User*.

Group users into access profiles and decide, from the menus of your database,
what they see and what they do: which apps and menus, which data and records,
which fields, buttons, tabs, reports and actions, and when and from where they
sign in. No code, and enforced on the server.

A user who carries no profile is not restricted in any way: the module does
nothing until you put someone in a profile.

Features
========

Profiles
--------

* **An app of its own**: Access Manager, on the home screen of the members of
  the *Access Management* group (the Administrator by default). Managing the
  profiles needs no Settings rights.
* **Who carries a profile**: users, the members of Odoo groups (joining and
  leaving with the group), every new internal user (*Give to New Users*), and
  users for a while, from one date to another, for a replacement during a
  leave. Set the profiles of many users at once from the Users list (*Action >
  Set Access Profiles*: add, remove or replace), and copy or move a user's
  access to another one (*Copy Access to...*).
* **Optional companies**: set them and the profile only applies to the users
  who have one of these companies.
* **Several profiles per user**, combined in one of two ways chosen per profile:

  * **Additive** profiles combine permissively with the other additive profiles
    of the same user: an operation is allowed as soon as one of them allows it,
    and something is hidden only when all of them hide it, as Odoo groups do.
  * **Override** profiles always apply and can never be overruled, which is
    what a blanket such as "Read Only" stacked on top of another profile needs.

* **Ready-made profiles**: *New from Template* offers a salesperson, sales read
  only, a CRM salesperson, an accountant without configuration, an auditor, a
  warehouse operator, a purchase user, a cashier, a manufacturing operator, a
  project team member, a timesheet user, an expenses user, an HR officer
  without salaries, and for any app a user without configuration or a read
  only user. The templates follow the apps installed: only those of the apps
  you have are offered, and installing an app later brings its template. The
  profile created is an ordinary one: change anything in it afterwards.
* A **home page** per profile: where its users land after signing in.

The menu tree
-------------

* **Configure everything from the menu tree.** The Menus & Apps tab shows the
  real menus of the database. Untick a menu to hide it with everything below
  it; click a menu to set, beside the tree, what its users may do there: its
  data and records, fields, buttons, tabs, filters, views, Print and Action
  menu entries and switches. Changes are saved at once.
* **A whole app at once**: on an app or a submenu, the same rights and records
  for everything below it, data added later by other modules included, with
  one-click levels (full access, no configuration, read only, no access). A
  submenu or a data below can be set apart: the closest setting wins. The
  records choice of an app leaves the data of its Configuration menus whole,
  and data other apps share (customers, products) is left alone unless asked.
* **Grant an app** a user's form leaves out: an app some user of the profile
  cannot open is shown unticked, marked *Not given*; ticking it gives them its
  user level (Purchase / User), and *Access to the app* picks another level.
  The profile then restricts it as usual. Taken away with the profile; groups
  that would make users administrators or access managers are never granted.
* Each menu shows marks for what is restricted on it, and *Only what is
  restricted* shows the whole profile at a glance. Odoo checks rights per data,
  not per menu: what is set on Quotations applies to Orders too (both open
  sales orders), and the panel says so.
* **Restrict an App**: an app on one screen, its menus, data, reports and
  Action menu entries, each with a checkbox, ticked for you by a level.

Data and records
----------------

* Read, edit, create and delete rights per data, enforced on the server, so the
  Create and Delete buttons leave the screen on their own.
* **Which records**, in one click: their own, their sales team, their
  companies, their warehouse, theirs and their team's in the org chart (three
  levels down, with Employees), created today, this week, this month or this
  year, edit drafts only; each offered only when the data has what it needs.
  Odoo's filter editor for anything else, evaluated like a standard access
  domain with ``user``, ``company_id`` and ``company_ids``. One filter applies
  to all four operations, and each operation can be narrowed further on its
  own: that is how you allow editing only draft records without hiding the
  others.
* **Allowed records**: only these journals, points of sale, warehouses,
  locations, sales teams or dashboards, and only what belongs to them (allowing
  two journals also filters their entries, journal items and payments). Pick
  them on the profile, or tick *Each User's Own* and set them on each user's
  form, so one profile serves every cashier, each on their own point of sale.

Fields
------

* Hide fields, make them read-only or required, always or only when a
  condition holds, remove the external link of a relational field, stop
  creating records from its dropdown, and filter the values it offers.
* Keep a field out of the exports while it stays on the screens.
* **Hide Costs and Margins** and **Hide Sales Prices**: one switch each, for the
  product cost, the margins and the stock valuation, or for the sales prices,
  discounts and amounts, in every app installed now or later.

Buttons, reports and actions
----------------------------

* Hide buttons, block them on the server, or both, always or once the record
  matches a condition. *Scan Buttons* reads them out of the views of a model,
  stat buttons, action buttons and the links of kanban cards included.
* Hide reports and the entries of the Action menu (server actions and window
  actions such as Send by Email), or the whole Print or Action menu of a model
  or of every model. They are refused when reached by their id or by their
  report URL too.

The screen
----------

* Hide notebook tabs (with a condition if you like), search filters and
  group-bys, the search panel, and whole view types such as Kanban.
* **The chatter**: hide it, or only *Send message* (only *Log note* remains),
  *Log note* (with both hidden, the chatter can only be read), the followers or
  the attachments; everywhere, or for one data. Posting is refused on the
  server too.
* **Activities**: everywhere or for one data, the Activity button and the
  activities leave the chatter, the lists and the kanban cards, the activity
  view leaves the menus and the data leaves the systray; scheduling, editing or
  marking one done there is refused on the server.
* Block export, import, archiving and duplication on the server; lock clickable
  status bars.
* **The search bar and the forms**: no custom filters, no custom group by, no
  saved searches, no new properties (saving a search and changing properties
  are refused on the server too).
* **The Settings**: hide the whole Settings app, or one of its apps (Sales,
  Inventory...) from Settings users, ticked on the Settings menu of the tree.
  What only a hidden app holds cannot be saved from a client either. Block
  installing, upgrading and uninstalling apps.

Sign-in
-------

* Working hours per day, in the timezone of the profile, allowed networks
  (addresses or ranges), and one session per user (signing in ends the user's
  other sessions). Checked at sign-in and on every request: a session ends when
  the working hours are over or when it is used from a network that is not
  allowed.
* Block the login of the users of a profile: every sign-in is refused, in the
  browser and through the external API, and their open sessions end at once.
  Their records stay untouched, and taking them out of the profile lets them
  back in, e.g. at the end of a leave.
* Block developer mode, and refuse XML-RPC and JSON-RPC sign-ins while leaving
  the browser working.

Checking and keeping track
--------------------------

* **Preview as User**: see Odoo exactly as a user sees it (their apps, menus,
  records, fields and buttons), read only, from the profile or the user form,
  without their password. A banner names the user and their profiles and
  leads back. Nothing is saved in a preview: the database refuses it, and a
  button says whether the user may use it instead of running it. What is read
  is logged as read by the person previewing. Only access managers may
  preview, and only users with no more rights than their own (Settings users
  may preview anyone but the administrator). The same screen lists what the
  user really ends up with and which profile produced each line.
* **Why?**: pick a user, a data, an operation and, if you like, a record, and
  see whether the user may do it and why: the access rules of their groups that
  grant it (or the groups that would), the rules that limit everyone, then each
  of their profiles, its menus and its record filter, the fields and buttons
  restricted there, and their recent refusals. From the Access Manager menu,
  the user form, the Effective Access window and every refusal of the audit log.
* **Health Check**: from the Access Manager menu, a profile, or the Action menu
  of the profiles list, and on its own every week. It lists what needs a look:
  rules lost with the menu, data or field they named (when a module is
  uninstalled or Odoo upgraded), rules naming a button, tab, filter or
  Settings app no view has any more, record filters and conditions that no
  longer evaluate, and allowed records or button actions deleted. Restore the
  last version to bring lost rules back, accept the profile as it is, or
  remove a dead rule in one click. It never changes a profile on its own; what
  it finds is noted in the chatter of the profile.
* **Effective access on the user form**: what the user really ends up with, all
  of their profiles combined.
* **History**: every change of a profile, of its switches and of its rules is
  logged in its chatter, with who made it and when.
* **Versions**: each save that changes a profile keeps a version of it, with
  who saved it and a summary. A version shows what it changed and what has
  changed since, line by line, and restores in one click: the profile becomes
  what it was, its users stay. Versions cannot be edited nor deleted; the last
  200 of each profile are kept.
* **Export and import** of profiles as a file, to build them on a test database
  and load them on production, sign-in rules included. Menus, reports, actions
  and allowed records are matched by external id, else by name; what the other
  database lacks is skipped and listed in the chatter of the profile. Users are
  matched by login, if asked.
* A refusal caused by a profile says so plainly, instead of Odoo's generic
  message, without naming the records refused.
* **Copy Restrictions**, because under a permissive union a restriction only
  bites when every additive profile of the user carries it.

Translations
============

The module is translated into Arabic, German, Spanish, French, Italian, Dutch,
Brazilian Portuguese, Russian, Turkish and Simplified Chinese. Missing your
language, or a better word? Write to odoomates@gmail.com.

Audit log
=========

The module depends on the free *User Audit & Sessions* app (``om_user_audit``),
which tells the calls a client makes apart from Odoo's own code. Every refusal
of a profile (a blocked button, a hidden action, report or field, a message
not allowed) lands in its log with the user, the record and the address, and
so do the sign-ins a profile refuses and the sessions it ends (working hours,
allowed networks, *One Session per User*), with the reason.

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

Upgrading Odoo
==============

Keep the module installed: the profiles, their users, versions and sign-in
rules are ordinary records, and they move with the database. A menu, a field
or a button the new Odoo no longer has can take a rule with it, so:

1. Upgrade a copy of the database first.
2. Run the **Health Check** on the upgraded copy, and set again what it lists.
3. Check the main profiles with **Preview as User**.
4. Go live.

Exporting the profiles before the upgrade, and importing what is missing after
it, is a second safety net.

Uninstallation
==============

Uninstalling the module removes the access profiles, and with them every group
a profile granted: the users keep the groups of their own form only, and every
restriction ends. The User Audit & Sessions app stays installed, with its log.

Configuration
=============

The module adds an **Access Manager** app to the home screen, for the members
of the *Access Management / Manager* group. The Administrator is one of them
from the installation on; add the other users who will manage the access
profiles on their user form. They need nothing else: no Settings rights.

Usage
=====

1. Create a profile, from a template or empty, and say who carries it: its
   **Users**, the members of Odoo groups (**And the members of**), or
   **Temporary Users**, from one date to another (included); these start and
   end on their own, in each user's time zone.
2. Open the **Menus & Apps** tab, the first one: untick what they must not see,
   click an app to pick a level (*Read only*, *No configuration*...), and click
   the menus that differ to set their rights, records, fields and buttons.
   Everything set beside the tree is saved at once and written in the history.
3. Set the **Switches** that apply to the whole system, and the **Sign-in**
   rules if needed.
4. Check the result with **Preview as User**, then let them work. The **Health
   Check** keeps an eye on the profiles every week.

In developer mode, more tabs list the same rules in full, and hold what belongs
to no menu: **Models** (the *Load Models* button fills it with the data
reachable through the menus the profile still shows), **Buttons** (the *Scan
Buttons* button reads them out of the views), **Fields**, **Pages**,
**Filters** and **Views** (tabs, search filters, view types and the apps of the
Settings), **Reports** and **Action Menu**.

A field, a button or a tab rule can carry a condition (*Only When*), written
like the conditions of Odoo's views: ``state == 'sale'``,
``amount_total > 1000 and not partner_id``. The rule then applies only to the
records matching it: the customer reference hidden on confirmed orders, the
discount locked above an amount, the Cancel button refused once an order is
confirmed. Fields compared with fixed values, ``uid``, ``and``, ``or`` and
``not`` are supported; anything else is refused when the rule is saved.

Limits
======

Read this before you use the module to protect anything that matters.

* **Hidden menus, tabs, filters and view types are cosmetic**: the record is
  still reachable by its URL or another menu. What the server refuses: the
  rights and record filters of the data, blocked buttons, hidden and read-only
  fields (at the boundary, see below), hidden reports and actions, the chatter
  and activity switches, the apps of the Settings, and export, import,
  archiving and duplication. This is why the default mode of a button rule is
  *Hide and block*, and why denying *Read* is the way to deny a data.
* **Hidden and read-only fields are enforced at the boundary, not inside
  Odoo.** What a user, the browser console or a script asks for (web client,
  XML-RPC and JSON-RPC) never carries a hidden value: it is stripped
  from what is read, and filtering, sorting, grouping or exporting on it is
  refused; what is written to a read-only or hidden field is ignored. A field
  hidden under a condition is blanked on the matching records only, but
  filtering, sorting and grouping on it are refused on all of them. Odoo's own
  code still reads and writes these fields as the user, on purpose: hiding the
  product cost must not stop a delivery from being validated. A report or a
  document Odoo builds itself (a PDF, an email) may therefore still show the
  value: hide that report too.
* **A hidden field stays in the screens, invisible**, with a blank value:
  other parts of a view may refer to it (a total, a condition), and fail when
  it is gone. It is removed from search, graph and pivot views, together with
  the search filters and group-bys using it.
* **A field's value filter is checked when a record is saved** from a client
  (web client, XML-RPC, JSON-RPC), lines of a one2many included: a
  value outside the filter is refused. A value the record already holds is
  left alone. A filter the server cannot evaluate on its own (one reading a
  value only the screen has) only narrows the dropdown. When several profiles
  set one on the same field, they combine like the rest: one additive
  profile's filter is enough, every override profile's filter applies.
* **A blocked button is refused from every client** (the web client, JSON-2,
  XML-RPC and JSON-RPC, clicked or called by hand), **whatever the view and the
  button id**: the server only learns which model and which method were
  called, so a rule that blocks a method blocks every button calling it.
* **Hiding the Print menu refuses every report of the model**, including one an
  email would attach.
* **A hidden view type is dropped from the action, not forbidden.** The last
  remaining view type of an action is always kept, so an action can never end
  up with nothing to render.
* **Hiding Send message or Log note only covers the chatter**, and what a
  client posts through the API. Odoo's own code still logs its notes (a
  validated delivery, a changed status). Sending by email from a document
  (*Send by Email*, a mail template) is a business flow and stays available:
  hide that action or its button too where it matters. Hiding the followers
  and the attachments is cosmetic.
* **Hidden activities are still planned by Odoo itself**: a confirmed document
  or an automation still schedules its next step for the user, it just does
  not show. Hide them for the data where nobody of the profile must follow
  them up.
* **A hidden app of the Settings only bites with Apply to Settings Users**:
  only Settings users open the Settings. A setting the app shares with another
  app shown, or one Odoo places outside of every app, stays editable there.
* **The companies of a profile follow the users, not the company switcher.** The
  profile applies to everyone who has one of them among theirs, whichever
  company they are working in. It cannot follow the switcher: core caches the
  menus per user with no company in the key, so a profile that changed with the
  active company would leave stale menus on screen.
* **Record filters reading the user** (``user.employee_id``) follow a change of
  that field of the user, or of an employee, at once. A filter reading deeper
  data of the user (their sales team's members) follows it at the next change
  of a profile or of the user: prefer the one-click choices, evaluated by the
  database.
* **A permissive union only ever widens.** Adding an additive profile to a user
  can only give access back, never take it away. Use an override profile, or
  copy the restrictions into every profile the user carries.
* **Granted access is real access.** A group granted by a profile gives what
  Odoo gives with it (its menus, its data, its record rules); the profile then
  takes away what it restricts. Removing the user from the profile, or
  archiving the profile, removes the group again, unless the user has it on
  their own form. Odoo 18 copies the groups a group implies onto the users:
  the profile remembers which ones it added, and takes back only those. A
  group set by hand on the user form after the profile gave it goes with the
  profile too: set it again if needed.
* **Allowed networks need the real address.** Behind a reverse proxy (nginx,
  a load balancer), start Odoo with ``--proxy-mode``, or every request comes
  from the proxy's address.
* **Blocking the external API blocks signing in, not the protocol.** A session
  already open, or a user without the flag, is unaffected.
* **A preview covers the whole session.** Every tab of the browser shows the
  previewed user until *Exit preview*, or for an hour at most. Sign-in rules
  (working hours, networks, one session) are not simulated: the preview shows
  the screens, the user form says when they could sign in. A page that writes
  something just to be shown (some dashboards record a first visit) answers
  with the preview's refusal.
* **The Health Check compares a profile with its last version.** A rule on a
  menu of your own (without an external id) that was renamed shows as lost
  although it is still there: accept it.
* **The last access manager is kept**: a change is refused when none of the
  members of *Access Management*, all their profiles combined, could still
  sign in, open the Access Manager app and edit the access profiles; so is
  archiving the last one, or taking them out of the group. The Access Manager
  app itself never appears in the menu tree.
* **The superuser and the Administrator user are never restricted**, whatever
  the profiles say. A member of the Settings group is only restricted by a
  profile that ticks *Apply to Settings Users*. This is deliberate: without it,
  a profile could leave the database with no way back in.
* Denying read on a model the interface needs will break the session of the
  users in that profile. Remove the profile from them to recover.
* **Speed.** Measured with 50 profiles and 2,000 rules: a user's rules are
  built once after each change (about 0.1 s) and then cached; a search costs
  nothing noticeable, and opening a screen about 7 ms more, its view being
  adapted to the user.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>

Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
