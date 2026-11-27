import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import sql

_logger = logging.getLogger(__name__)

# (table, old column, new column): the data that moves to the fields of the Social Inbox
COPIES = [
    ('discuss_channel', 'om_whatsapp_account_id', 'om_social_account_id'),
    ('discuss_channel', 'om_whatsapp_number', 'om_social_address'),
    ('discuss_channel', 'om_whatsapp_partner_id', 'om_social_partner_id'),
    ('discuss_channel', 'om_whatsapp_last_incoming', 'om_social_last_incoming'),
    ('discuss_channel', 'om_whatsapp_profile_name', 'om_social_profile_name'),
    ('discuss_channel', 'om_whatsapp_picture_date', 'om_social_picture_date'),
    ('discuss_channel', 'om_whatsapp_res_model', 'om_social_res_model'),
    ('discuss_channel', 'om_whatsapp_res_id', 'om_social_res_id'),
    ('mail_message', 'om_whatsapp_account_id', 'om_social_account_id'),
    ('mail_message', 'om_whatsapp_id', 'om_social_message_id'),
    ('mail_message', 'om_whatsapp_receipt', 'om_social_receipt'),
]


def migrate(cr, version):
    """ The data of the WhatsApp fields goes to the fields of the Social
    Inbox; the WhatsApp user IDs of the contacts and of the conversations
    become identities. Every value is checked: a difference stops the
    upgrade, which is rolled back. """
    if not sql.table_exists(cr, 'om_whatsapp_account'):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    for table, old, new in COPIES:
        if sql.column_exists(cr, table, old):
            where = "channel_type = 'om_social'" if table == 'discuss_channel' else f'"{old}" IS NOT NULL'
            cr.execute(f'UPDATE "{table}" SET "{new}" = "{old}" WHERE {where}')
    if sql.column_exists(cr, 'mail_notification', 'om_whatsapp_number'):
        user_id = 'om_whatsapp_user_id' if sql.column_exists(cr, 'mail_notification', 'om_whatsapp_user_id') else 'NULL'
        cr.execute(f"""
            UPDATE mail_notification
               SET om_social_address = COALESCE(NULLIF(om_whatsapp_number, ''), {user_id})
             WHERE notification_type = 'om_social'
        """)
    _make_identities(env)
    check(cr)


def _make_identities(env):
    cr = env.cr
    Identity = env['om.social.identity']
    by_user_ref = {}  # user ID: identities
    by_address = {}  # number: identities
    if sql.column_exists(cr, 'res_partner', 'om_whatsapp_user_id'):
        username = 'om_whatsapp_username' if sql.column_exists(cr, 'res_partner', 'om_whatsapp_username') else 'NULL'
        cr.execute(f"""
            SELECT id, om_whatsapp_user_id, {username} FROM res_partner
             WHERE om_whatsapp_user_id IS NOT NULL AND om_whatsapp_user_id != '' ORDER BY id
        """)
        rows = cr.fetchall()
        identities = Identity.create([{
            'channel': 'whatsapp', 'partner_id': partner_id, 'user_ref': user_ref, 'username': name or False,
        } for partner_id, user_ref, name in rows])
        for identity in identities:
            by_user_ref.setdefault(identity.user_ref, []).append(identity)
        _logger.info("%s identities from the WhatsApp user IDs of the contacts", len(identities))

    has_user_id = sql.column_exists(cr, 'discuss_channel', 'om_whatsapp_user_id')
    cr.execute(f"""
        SELECT id, om_whatsapp_account_id, om_whatsapp_number, om_whatsapp_partner_id, om_whatsapp_profile_name,
               {'om_whatsapp_user_id, om_whatsapp_username' if has_user_id else 'NULL, NULL'}
          FROM discuss_channel WHERE channel_type = 'om_social' ORDER BY id
    """)
    used = set()  # (account, identity): one conversation of an account per identity
    count = 0
    for channel_id, account_id, number, partner_id, profile_name, user_ref, username in cr.fetchall():
        candidates = by_user_ref.get(user_ref, []) if user_ref else by_address.get(number, []) if number else []
        candidates = [i for i in candidates if (account_id, i.id) not in used
                      and (not partner_id or not i.partner_id or i.partner_id.id == partner_id)]
        candidates.sort(key=lambda i: (i.partner_id.id != partner_id, not i.partner_id, i.id))
        identity = candidates[0] if candidates else None
        if identity:
            values = {}
            if number and not identity.address:
                values['address'] = number
            if username and not identity.username:
                values['username'] = username
            if profile_name and not identity.profile_name:
                values['profile_name'] = profile_name
            if partner_id and not identity.partner_id:
                values['partner_id'] = partner_id
            if values:
                identity.write(values)
        else:
            identity = Identity.create({
                'channel': 'whatsapp', 'address': number or False, 'user_ref': user_ref or False,
                'username': username or False, 'profile_name': profile_name or False, 'partner_id': partner_id or False,
            })
            count += 1
            if user_ref:
                by_user_ref.setdefault(user_ref, []).append(identity)
        if number and identity not in by_address.setdefault(number, []):
            by_address[number].append(identity)
        used.add((account_id, identity.id))
        cr.execute("UPDATE discuss_channel SET om_social_identity_id = %s WHERE id = %s", [identity.id, channel_id])
    env['om.social.identity'].flush_model()
    _logger.info("%s identities from the WhatsApp conversations", count)


def check(cr):
    """ Every value is where it was: raise on the first difference. """
    problems = []

    def count(label, query):
        cr.execute(query)
        found = cr.fetchone()[0]
        if found:
            problems.append(f"{label}: {found}")

    cr.execute("SELECT COUNT(*) FROM om_whatsapp_account")
    accounts = cr.fetchone()[0]
    count("WhatsApp accounts not copied", """
        SELECT COUNT(*) FROM om_whatsapp_account old LEFT JOIN om_social_account new ON new.id = old.id
         WHERE new.id IS NULL OR new.name IS DISTINCT FROM old.name OR new.company_id IS DISTINCT FROM old.company_id
            OR new.provider IS DISTINCT FROM old.provider OR new.active IS DISTINCT FROM old.active
    """)
    if sql.table_exists(cr, 'om_whatsapp_account_res_users_rel'):
        count("users of the accounts not copied", """
            SELECT COUNT(*) FROM om_whatsapp_account_res_users_rel old
              LEFT JOIN om_social_account_res_users_rel new
                ON new.om_social_account_id = old.om_whatsapp_account_id AND new.res_users_id = old.res_users_id
             WHERE new.res_users_id IS NULL
        """)
    differ = ' OR '.join(f'"{new}" IS DISTINCT FROM "{old}"' for table, old, new in COPIES
                         if table == 'discuss_channel' and sql.column_exists(cr, table, old))
    count("conversations not copied", f"SELECT COUNT(*) FROM discuss_channel WHERE channel_type = 'om_social' AND ({differ})")
    count("conversations without their account", """
        SELECT COUNT(*) FROM discuss_channel WHERE channel_type = 'om_social'
           AND (om_social_account_id IS NULL OR om_social_account_id NOT IN (SELECT id FROM om_social_account))
    """)
    count("conversations still WhatsApp", "SELECT COUNT(*) FROM discuss_channel WHERE channel_type = 'om_whatsapp'")
    count("conversations without identity", """
        SELECT COUNT(*) FROM discuss_channel WHERE channel_type = 'om_social' AND om_social_identity_id IS NULL
    """)
    if sql.column_exists(cr, 'discuss_channel', 'om_whatsapp_user_id'):
        count("conversations without their WhatsApp user ID", """
            SELECT COUNT(*) FROM discuss_channel channel JOIN om_social_identity identity
                ON identity.id = channel.om_social_identity_id
             WHERE channel.channel_type = 'om_social' AND channel.om_whatsapp_user_id IS NOT NULL
               AND identity.user_ref IS DISTINCT FROM channel.om_whatsapp_user_id
        """)
    differ = ' OR '.join(f'"{new}" IS DISTINCT FROM "{old}"' for table, old, new in COPIES
                         if table == 'mail_message' and sql.column_exists(cr, table, old))
    count("messages not copied", f"SELECT COUNT(*) FROM mail_message WHERE {differ}")
    count("messages still WhatsApp", "SELECT COUNT(*) FROM mail_message WHERE message_type = 'om_whatsapp'")
    if sql.column_exists(cr, 'mail_notification', 'om_whatsapp_number'):
        user_id = 'om_whatsapp_user_id' if sql.column_exists(cr, 'mail_notification', 'om_whatsapp_user_id') else 'NULL'
        count("notifications not copied", f"""
            SELECT COUNT(*) FROM mail_notification WHERE notification_type = 'om_social'
               AND om_social_address IS DISTINCT FROM COALESCE(NULLIF(om_whatsapp_number, ''), {user_id})
        """)
    count("notifications still WhatsApp", "SELECT COUNT(*) FROM mail_notification WHERE notification_type = 'om_whatsapp'")
    if sql.column_exists(cr, 'res_partner', 'om_whatsapp_user_id'):
        count("contacts without their WhatsApp user ID", """
            SELECT COUNT(*) FROM res_partner partner
             WHERE partner.om_whatsapp_user_id IS NOT NULL AND partner.om_whatsapp_user_id != ''
               AND NOT EXISTS (SELECT 1 FROM om_social_identity identity
                                WHERE identity.partner_id = partner.id
                                  AND identity.user_ref = partner.om_whatsapp_user_id)
        """)
    if problems:
        raise RuntimeError("The WhatsApp data did not move to the Social Inbox, the upgrade stops: " + '; '.join(problems))
    _logger.info("WhatsApp on the Social Inbox: %s account(s), every conversation, message and notification checked",
                 accounts)
