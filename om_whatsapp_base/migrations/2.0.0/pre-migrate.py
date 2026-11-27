import logging

from odoo.tools import sql

_logger = logging.getLogger(__name__)

# the values of the selections that move to the Social Inbox: renamed before the fields are loaded, else the
# removal of the old value deletes the records that have it (conversations, notifications)
SELECTIONS = [
    ('discuss_channel', 'channel_type', 'om_whatsapp', 'om_social'),
    ('mail_message', 'message_type', 'om_whatsapp', 'om_social'),
    ('mail_notification', 'notification_type', 'om_whatsapp', 'om_social'),
    ('mail_notification', 'failure_type', 'om_whatsapp_error', 'om_social_error'),
]
# the columns that name a model
MODEL_REFERENCES = [
    ('mail_message', 'model'),
    ('mail_followers', 'res_model'),
    ('mail_activity', 'res_model'),
    ('mail_activity_type', 'res_model'),
    ('mail_message_subtype', 'res_model'),
    ('ir_attachment', 'res_model'),
    ('ir_model_data', 'model'),
    ('ir_filters', 'model_id'),
    ('ir_exports', 'resource'),
    ('ir_act_window', 'res_model'),
    ('ir_act_server', 'model_name'),
    ('ir_model_fields', 'relation'),
    ('rating_rating', 'res_model'),
    ('rating_rating', 'parent_res_model'),
]
# the columns that link a model by its id in ir_model
MODEL_ID_REFERENCES = [
    ('ir_act_server', 'model_id'),
    ('ir_act_server', 'binding_model_id'),
    ('ir_act_window', 'binding_model_id'),
    ('ir_act_report_xml', 'binding_model_id'),
    ('mail_activity', 'res_model_id'),
    ('base_automation', 'model_id'),
]
OLD_MODEL, NEW_MODEL = 'om.whatsapp.account', 'om.social.account'


def migrate(cr, version):
    """ WhatsApp moves onto the Social Inbox (om_social_base, installed just
    before): the accounts become social accounts with the same ids, the
    WhatsApp values of the selections become the social ones, and whatever
    named the old model names the new one. The data of the fields is copied
    in post-migrate, the old columns dropped in end-migrate. """
    if not sql.table_exists(cr, 'om_whatsapp_account'):
        return
    if not sql.table_exists(cr, 'om_social_account'):
        raise RuntimeError("om_social_base must be installed before om_whatsapp_base is migrated.")

    for table, column, old, new in SELECTIONS:
        if sql.column_exists(cr, table, column):
            cr.execute(f'UPDATE "{table}" SET "{column}" = %s WHERE "{column}" = %s', [new, old])
            _logger.info("%s.%s: %s -> %s on %s row(s)", table, column, old, new, cr.rowcount)

    _copy_accounts(cr)
    _repoint_model(cr)
    _drop_foreign_keys(cr)
    # the cron of the profile pictures is the one of om_social_base now
    cr.execute("""
        SELECT data.id, cron.id, cron.ir_actions_server_id FROM ir_model_data data
          JOIN ir_cron cron ON cron.id = data.res_id
         WHERE data.module = 'om_whatsapp_base' AND data.name = 'ir_cron_om_whatsapp_pictures' AND data.model = 'ir.cron'
    """)
    for data_id, cron_id, action_id in cr.fetchall():
        cr.execute("DELETE FROM ir_cron WHERE id = %s", [cron_id])
        cr.execute("DELETE FROM ir_act_server WHERE id = %s", [action_id])
        cr.execute("DELETE FROM ir_model_data WHERE id = %s", [data_id])
    # the composers are transient: they are made again
    if sql.table_exists(cr, 'om_whatsapp_composer'):
        cr.execute("DELETE FROM om_whatsapp_composer")


def _columns(cr, table):
    cr.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
               "AND table_name = %s", [table])
    return {row[0] for row in cr.fetchall()}


def _copy_accounts(cr):
    """ Each WhatsApp account becomes a social account of the channel
    WhatsApp, with its id: every record that points to it keeps its value. """
    old = _columns(cr, 'om_whatsapp_account')
    cr.execute("SELECT id FROM om_social_account WHERE id IN (SELECT id FROM om_whatsapp_account)")
    if taken := [row[0] for row in cr.fetchall()]:
        raise RuntimeError(f"The social accounts {taken} have the ids of WhatsApp accounts: they cannot be migrated.")
    values = {
        'id': 'id',
        'name': 'name',
        'active': 'active',
        'sequence': 'COALESCE(sequence, 10)',
        'channel': "'whatsapp'",
        'provider': "COALESCE(provider, 'link')",
        'address': 'phone' if 'phone' in old else 'NULL',
        'company_id': 'company_id',
        'reply_days': 'reply_days' if 'reply_days' in old else '7',
        'fetch_pictures': 'COALESCE(fetch_pictures, TRUE)' if 'fetch_pictures' in old else 'TRUE',
        'receive_unknown': 'COALESCE(receive_unknown, TRUE)' if 'receive_unknown' in old else 'TRUE',
        'create_uid': 'create_uid',
        'create_date': 'create_date',
        'write_uid': 'write_uid',
        'write_date': 'write_date',
    }
    cr.execute(f"""
        INSERT INTO om_social_account ({', '.join(values)})
        SELECT {', '.join(values.values())} FROM om_whatsapp_account
    """)
    _logger.info("%s WhatsApp account(s) copied to the Social Inbox", cr.rowcount)
    cr.execute("""
        SELECT setval(pg_get_serial_sequence('om_social_account', 'id'),
                      GREATEST((SELECT MAX(id) FROM om_social_account), 1),
                      (SELECT MAX(id) FROM om_social_account) IS NOT NULL)
    """)
    if sql.table_exists(cr, 'om_whatsapp_account_res_users_rel'):
        cr.execute("""
            INSERT INTO om_social_account_res_users_rel (om_social_account_id, res_users_id)
            SELECT om_whatsapp_account_id, res_users_id FROM om_whatsapp_account_res_users_rel
            ON CONFLICT DO NOTHING
        """)


def _repoint_model(cr):
    """ What names the old model names the new one: the files, followers,
    activities and external ids of the accounts, the scheduled actions on
    them, the filters, the custom fields that link them. Else Odoo deletes
    them with the old model. """
    for table, column in MODEL_REFERENCES:
        if sql.column_exists(cr, table, column):
            cr.execute(f'UPDATE "{table}" SET "{column}" = %s WHERE "{column}" = %s', [NEW_MODEL, OLD_MODEL])
    cr.execute("SELECT model, id FROM ir_model WHERE model IN %s", [(OLD_MODEL, NEW_MODEL)])
    ids = dict(cr.fetchall())
    if OLD_MODEL in ids and NEW_MODEL in ids:
        for table, column in MODEL_ID_REFERENCES:
            if sql.column_exists(cr, table, column):
                cr.execute(f'UPDATE "{table}" SET "{column}" = %s WHERE "{column}" = %s', [ids[NEW_MODEL], ids[OLD_MODEL]])


def _drop_foreign_keys(cr):
    """ The foreign keys to the old table go: the columns that stay (the
    account of a template, of a server action) get theirs to the new table
    when their fields are loaded, the others are dropped. """
    cr.execute("""
        SELECT con.conname, rel.relname FROM pg_constraint con
          JOIN pg_class rel ON rel.oid = con.conrelid
         WHERE con.contype = 'f' AND con.confrelid = 'om_whatsapp_account'::regclass
    """)
    for name, table in cr.fetchall():
        sql.drop_constraint(cr, table, name)
