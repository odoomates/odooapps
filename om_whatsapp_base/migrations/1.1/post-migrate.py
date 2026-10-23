CLEAN = "(CASE WHEN left({n}, 1) = '+' THEN '+' ELSE '' END || regexp_replace({n}, '[^0-9]', '', 'g'))"


def migrate(cr, version):
    """ Numbers kept as typed (+32 470 55 51 23) become +32470555123, as the
    replies give them: one conversation for each customer. A conversation
    whose clean number already has one keeps its number. """
    cr.execute(f"""
        UPDATE mail_notification
           SET om_whatsapp_number = {CLEAN.format(n='om_whatsapp_number')}
         WHERE notification_type = 'om_whatsapp' AND om_whatsapp_number ~ '[^0-9+]'
    """)
    cr.execute(f"""
        UPDATE discuss_channel channel
           SET om_whatsapp_number = {CLEAN.format(n='channel.om_whatsapp_number')}
         WHERE channel.channel_type = 'om_whatsapp' AND channel.om_whatsapp_number ~ '[^0-9+]'
           AND NOT EXISTS (
               SELECT 1 FROM discuss_channel other
                WHERE other.channel_type = 'om_whatsapp'
                  AND other.om_whatsapp_account_id = channel.om_whatsapp_account_id
                  AND other.om_whatsapp_number = {CLEAN.format(n='channel.om_whatsapp_number')})
    """)
