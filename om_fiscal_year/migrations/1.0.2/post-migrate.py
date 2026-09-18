"""Repair the fallout of the lock-date aliasing bug.

Until 1.0.2 the settings fields ``tax_lock_date``, ``sale_lock_date`` and
``purchase_lock_date`` were all declared as ``related='company_id.hard_lock_date'``.
Setting any of them from Accounting Settings therefore wrote the company's
**Hard Lock Date** instead, and the three real columns could never be filled in
that way.

What this script does:

* copies ``hard_lock_date`` into the three soft lock columns when they are empty.
  A hard lock blocks strictly more than a tax/sale/purchase lock on the same
  date, so this cannot restrict anything that was not already restricted: it
  only stops the Settings page from looking like the upgrade wiped the values.

What this script deliberately does NOT do:

* clear ``hard_lock_date``. The old page also had a genuine "Hard Lock Date"
  field bound to the very same column, so there is no way to tell a wanted hard
  lock from one set by mistake, and Odoo refuses to remove or lower a hard lock
  (``res.company._validate_locks``). Removing an accounting lock is an explicit
  decision for the administrator, not something an upgrade should do silently.
  Affected companies are listed in the log with the SQL to do it by hand.
"""

import logging

_logger = logging.getLogger(__name__)

LOCK_FIELDS = ('tax_lock_date', 'sale_lock_date', 'purchase_lock_date')


def migrate(cr, version):
    if not version:
        # fresh install, nothing to repair
        return

    cr.execute("""
        SELECT id, name, hard_lock_date, tax_lock_date, sale_lock_date, purchase_lock_date
          FROM res_company
         WHERE hard_lock_date IS NOT NULL
      ORDER BY id
    """)
    companies = cr.dictfetchall()
    if not companies:
        return

    # A company whose three soft locks are all empty could never have set them
    # through the settings page, which is the signature of the bug.
    suspects = [c for c in companies if not any(c[f] for f in LOCK_FIELDS)]

    for field in LOCK_FIELDS:
        cr.execute("""
            UPDATE res_company
               SET {field} = hard_lock_date
             WHERE hard_lock_date IS NOT NULL
               AND {field} IS NULL
        """.format(field=field))
        if cr.rowcount:
            _logger.info(
                "om_fiscal_year: copied hard_lock_date into %s on %s compan%s",
                field, cr.rowcount, 'y' if cr.rowcount == 1 else 'ies',
            )

    if suspects:
        listed = ", ".join("%s (id=%s, %s)" % (c['name'], c['id'], c['hard_lock_date'])
                           for c in suspects)
        _logger.warning(
            "om_fiscal_year: these companies have a Hard Lock Date that may have been "
            "set by mistake, because earlier versions of this module wrote it whenever "
            "the Tax / Sales / Purchase Lock Date was saved: %s.\n"
            "Odoo does not allow a Hard Lock Date to be removed or moved back, so if it "
            "was not intended it has to be cleared directly in the database, for example:\n"
            "    UPDATE res_company SET hard_lock_date = NULL WHERE id IN (%s);\n"
            "Review each company before doing so: a Hard Lock Date that was set on "
            "purpose must be kept.",
            listed, ", ".join(str(c['id']) for c in suspects),
        )
