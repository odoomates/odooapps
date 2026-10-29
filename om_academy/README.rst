====================================
Odoo Mates Academy: Odoo Development
====================================

.. note::

   **Made for learning.** New to coding, or to Odoo? This module is for you:
   install it on a test database and try it out. No experience needed.

   **Completely free, and open source (LGPL-3).** Tell us which course you want
   next, at odoomates@gmail.com.

Learn Odoo development inside Odoo: pick a course and build a real app, step by
step. The Academy is not an app to run a business: it is a place to learn, from
an empty folder to a working app.

For beginners first
===================

* **A story, not a manual**: each step answers the question the step before
  left open. The app exists, but where are its records kept? A table. Who may
  see them? Access rights. Where do users click? A menu...
* **Every new word explained**: model, field, access right, group, action,
  menu, view, domain... in plain words, in a *New words* box, the first time
  you meet them.
* **One step at a time**: *Next* opens once the step is built (or checked, in
  code), and the steps after it stay locked.
* **Watch the code grow**: on wide screens, the whole module stands beside the
  step. Click any file to see its code after this step, with the lines the
  step added in green. Drag its edge to make it wider.
* **Under the hood**: the tables of your app in PostgreSQL, live, when you want
  to look.

Two ways to build
=================

* **Build it live**: no editor needed. The Academy creates in your database what
  the step's code would, and tells you what Odoo stored. Undo any step, start
  over, and export the app as a module at the end.
* **Code it**: write the files in your editor. Install or upgrade the module
  from the screen, and let the Academy check it: models, fields, views, menus,
  access rights and computed fields, with a precise message and a hint for
  whatever is missing. Stuck? *Write it for me*, or compare your files with the
  course's.

  *Fresh out of the oven*: Code it is not tested as much as Build it live yet.
  Something may break here and there... and that is your chance: fix it for
  us, and open a pull request.

You can switch modes at any time; *Continue in code* writes what you built live
into your addons folder.

Courses
=======

* **Build your first app** (beginner, 10 steps): a module from an empty folder,
  models, access rights, an action and menus, form, list and search views, a
  many2one, a status with buttons, a computed field. Pick what it is about:
  Library, Car Rental, Hotel or Tool Lending. *Basic + a little more* adds
  fields locked or required by the status, a chatter, and tracking.
* **Extend Odoo: members in Contacts** (beginner, 6 steps): fields added to
  ``res.partner`` with ``_inherit``, Odoo's own views extended with XPath, a
  computed field.
* **Organize with a Kanban board** (intermediate, 5 steps): stages loaded as
  data, a link, and the Kanban view of Odoo 20.
* **Print a PDF report** (intermediate, 5 steps): a report in the Print menu, a
  QWeb template, a paper format.
* **Secure an app, the Odoo 20 way** (intermediate, 7 steps): groups under a
  privilege, access rights per group, a domain so that users see only their own
  records, menus and fields for managers only.
* **Your first Owl components** (intermediate, 5 steps, Code it only): a client
  action of your own, its state, a child component with props, data read with
  the ORM service, a notification and an action. Odoo 20's Owl: ``proxy``,
  ``useProps``.

At the end of a course: your certificate (PDF), trophies, challenges to do on
your own, and the app to export.

Warm-up
=======

* **Quiz**: rounds of 8 questions, on Odoo, on field types, or on what you
  built (questions open as you complete the steps). The questions you have seen
  the least come first, and questions and answers are shuffled: each round is a
  new set. Your scores are kept: your last rounds and your best per topic.
* **Hands-on**: small tasks done in Odoo by hand (a contact, a user, an app, a
  message in a chatter), checked in the database.
* **Find it**: what a developer looks for every day, explained, then found by
  you: the browser console, the developer mode, the model of a page, the id of
  a record, an external id, the id of a view.

Bug hunt
========

Fourteen errors every Odoo developer meets: a missing comma in the manifest, a
model never imported, a field the view does not know, *Expected singleton*, a
compute that forgets a record, a template that does not exist... For each one:
the code, the error exactly as Odoo shows it, and four reasons. Pick the right
one: wrong, you get a hint and try again; right, you read why, and the fix.

Videos
======

The Odoo development videos of Odoo Mates on YouTube, all on the home screen,
and on each step the ones that explain it. Recorded on Odoo 17: most of it is
the same in Odoo 18, 19 and 20, and the courses show the Odoo 20 way where it
changed.

Before *Code it*, the first videos of the Odoo 16 playlist set up Odoo on your
own computer: Odoo with PyCharm, a custom addons path, a first module. Like
them? Subscribe to the channel: https://www.youtube.com/@OdooMates

And more
========

* **Your journey**: the courses as stops on a path, the next one glowing, the
  ones done stamped.
* **Day streak**: the days in a row you learned something, and your best.
* **Your app in numbers**: at the end of a course, the lines, files, models,
  fields, views and menus you wrote.
* **Interview round**: a topic of the warm-up with the questions of a job
  interview for an Odoo developer.

In your language
================

The whole Academy, its courses, the bug hunt and the quiz included, is
translated into Arabic, Chinese (Simplified), Dutch, French, German,
Indonesian, Italian, Japanese, Portuguese (Brazil), Russian, Spanish and
Turkish. The code stays in English, and so do the names of the app you build.

Usage
=====

Open the **Academy** app (administrators only), pick a course and a mode. Start
with *Build your first app* in *Build it live* if you have never written code.

Limits
======

* **Learn on a test database.** Build it live creates real models, fields,
  views and menus (named with ``x_``, as Odoo requires for what is not in a
  module). Undo and *Start this course over* remove them.
* **One live build of a course per database**: a second learner is told who
  built it.
* **Code it needs a local or development Odoo** with an addons folder you can
  write to. *Write it for me* writes only into the folder you pick, or into
  Odoo's own addons folder of your user when it is writable; it never picks a
  folder of other modules on its own. A new Python file needs a restart of
  Odoo; start it with ``--dev=reload,xml`` and it restarts by itself.
* In Build it live a method becomes a server action, and a field cannot default
  to the current user; the steps say so where it matters.

Found a bug?
============

Lucky you: you just found your homework. 🐛

We could fix it... but where is the fun in that? This app is for learning, and
that bug is yours: catch it, squash it, open a pull request on
https://github.com/odoomates/odooapps, and brag about it.

Tried, and the bug won? No shame, bugs win sometimes. Tell us, in an issue
there or at odoomates@gmail.com, and we will fight it together.

Credits
=======

* Odoo Mates <odoomates@gmail.com>
