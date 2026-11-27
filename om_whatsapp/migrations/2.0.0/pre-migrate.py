from odoo.tools import sql

PREFIXES = ('meta_',)


def migrate(cr, version):
    """ The Meta fields of the WhatsApp accounts go to the social accounts,
    which have the same ids: the columns are made before the fields are
    loaded, so that Odoo keeps their values instead of filling in defaults. """
    if not (sql.table_exists(cr, 'om_whatsapp_account') and sql.table_exists(cr, 'om_social_account')):
        return
    cr.execute("""
        SELECT attname, format_type(atttypid, atttypmod) FROM pg_attribute
         WHERE attrelid = 'om_whatsapp_account'::regclass AND attnum > 0 AND NOT attisdropped
    """)
    columns = [(name, kind) for name, kind in cr.fetchall() if name.startswith(PREFIXES)]
    for name, kind in columns:
        if not sql.column_exists(cr, 'om_social_account', name):
            cr.execute(f'ALTER TABLE om_social_account ADD COLUMN "{name}" {kind}')
    if columns:
        assignments = ', '.join(f'"{name}" = old."{name}"' for name, _kind in columns)
        cr.execute(f"UPDATE om_social_account new SET {assignments} FROM om_whatsapp_account old WHERE old.id = new.id")
    cr.execute(f"""
        SELECT COUNT(*) FROM om_whatsapp_account old JOIN om_social_account new ON new.id = old.id
         WHERE {' OR '.join(f'new."{name}" IS DISTINCT FROM old."{name}"' for name, _kind in columns) or 'FALSE'}
    """)
    if differ := cr.fetchone()[0]:
        raise RuntimeError(f"{differ} account(s) did not keep their {', '.join(PREFIXES)} fields: the upgrade stops.")
