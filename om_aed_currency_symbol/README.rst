=======================
UAE Dirham Symbol (AED)
=======================

A bridge until Odoo supports the sign.

The UAE Dirham sign (U+20C3) is new: it joined Unicode in version 18.0, and Odoo still shows 'AED' by default.

This module displays the official sign today, using a small font for devices that don't support it yet.

Once Odoo supports the sign natively, we'll announce it here and discontinue this module.

Uninstalling the module restores 'AED', or Odoo's own sign if supported, without changing anything else in your database.

Features
========

Shows the UAE Dirham sign (U+20C3 UAE DIRHAM SIGN, Unicode 18.0) for the AED currency in the Odoo
backend, PDF reports, website, customer portal and Point of Sale.

* Uses the official Unicode character, so copied amounts keep the real sign.
* The sign is placed before the amount. A symbol typed by the user is kept; the button *Use UAE
  Dirham Sign* on the currency form switches to the sign.
* Symbols set by older workarounds (for example U+1D01) are replaced automatically.
* Works with every report layout font (Lato, Roboto, Open Sans, Montserrat, Oswald, Raleway,
  Tajawal, Fira Mono), regular and bold.
* No element's ``font-family`` is changed: interface fonts, report fonts and code editors
  (Ace/CodeMirror monospace) keep their own fonts.

How it works
============

* On install, the AED currency symbol becomes U+20C3, placed before the amount.
* A tiny web font (one glyph, regular and bold, in ``static/src/fonts``) is declared with
  ``@font-face`` rules restricted with ``unicode-range: U+20C3`` and added to font families that
  already exist in Odoo's stacks (``Odoo Unicode Support Noto``, and the report layout fonts in the
  report bundle).
* The CSS references the font files by URL instead of embedding them, so each font file is
  downloaded once and cached, and the report stylesheet stays small.
* On uninstall, the symbol of AED is set back to ``AED``, placed after the amount, but only if it is
  still the Dirham sign set by this module. A symbol typed by the user is never changed. If Odoo's own
  currency data already uses U+20C3 (a future Odoo version), the symbol is left untouched.

Font origin and license
=======================

The font files in ``static/src/fonts`` contain a single glyph, U+20C3 UAE DIRHAM SIGN, in a regular
and a bold weight (TTF, WOFF, WOFF2).

* **Creator:** the glyph outline (``om_uae_dirham.svg``) was drawn for this module by Akshay Manoj,
  with the help of an AI tool, and the fonts were built from it. It is not taken from any third-party
  font.
* **License:** LGPL-3, the same license as the module (also recorded in the copyright field of the
  font files). No third-party font software is included.
* **Design:** the glyph follows the official sign published by the Central Bank of the UAE.

Tests
=====

::

    odoo-bin -d <db> -i om_aed_currency_symbol,web_tour --test-enable --test-tags=/om_aed_currency_symbol

Credits
=======

Contributors
------------

Akshay Manoj

Author & Maintainer
-------------------

This module is maintained by the Odoo Mates <odoomates@gmail.com>

License
=======

LGPL-3
