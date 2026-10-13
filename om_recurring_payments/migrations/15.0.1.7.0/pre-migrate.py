from odoo.tools.sql import column_exists, create_column


def migrate(cr, version):
    # The currency and the journal of the recurring payments used to be read from the company and
    # the template, and are stored from now on. The existing records keep what they showed until
    # now: the currency of their company and the journal of their template. Only the new ones take
    # the currency of their journal.
    for table in ('recurring_payment', 'recurring_payment_line'):
        if not column_exists(cr, table, 'currency_id'):
            create_column(cr, table, 'currency_id', 'int4')
            cr.execute(f"""
                UPDATE {table} rec
                   SET currency_id = company.currency_id
                  FROM res_company company
                 WHERE company.id = rec.company_id
            """)
    if not column_exists(cr, 'recurring_payment', 'journal_id'):
        create_column(cr, 'recurring_payment', 'journal_id', 'int4')
        cr.execute("""
            UPDATE recurring_payment rec
               SET journal_id = template.journal_id
              FROM account_recurring_template template
             WHERE template.id = rec.template_id
        """)
