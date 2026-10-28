# The company of a profile became its companies: copy the old column into the
# new relation, then drop it.
from odoo.tools import sql


def migrate(cr, version):
    if not sql.column_exists(cr, 'om_access_profile', 'company_id'):
        return
    cr.execute("""
        INSERT INTO om_access_profile_company_rel (profile_id, company_id)
             SELECT id, company_id
               FROM om_access_profile
              WHERE company_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    cr.execute("ALTER TABLE om_access_profile DROP COLUMN company_id")
