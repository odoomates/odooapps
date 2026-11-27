import logging
from pathlib import Path

from odoo.modules.module import load_script
from odoo.tools import sql

_logger = logging.getLogger(__name__)

# the WhatsApp columns whose data is in the fields of the Social Inbox now
OLD_COLUMNS = {
    'discuss_channel': [
        'om_whatsapp_account_id', 'om_whatsapp_number', 'om_whatsapp_user_id', 'om_whatsapp_username',
        'om_whatsapp_partner_id', 'om_whatsapp_last_incoming', 'om_whatsapp_profile_name', 'om_whatsapp_picture_date',
        'om_whatsapp_res_model', 'om_whatsapp_res_id',
    ],
    'mail_message': ['om_whatsapp_account_id', 'om_whatsapp_id', 'om_whatsapp_receipt'],
    'mail_notification': ['om_whatsapp_number', 'om_whatsapp_user_id'],
    'res_partner': ['om_whatsapp_user_id', 'om_whatsapp_username'],
}


def migrate(cr, version):
    """ The data of WhatsApp is in the Social Inbox, checked again now that
    every module is loaded: the old columns and the old table of the
    accounts go (the provider modules copied theirs in their own scripts). """
    if not sql.table_exists(cr, 'om_whatsapp_account'):
        return
    post = load_script(str(Path(__file__).with_name('post-migrate.py')), 'om_whatsapp_base_post_migrate')
    post.check(cr)
    for table, columns in OLD_COLUMNS.items():
        for column in columns:
            if sql.column_exists(cr, table, column):
                cr.execute(f'ALTER TABLE "{table}" DROP COLUMN "{column}" CASCADE')
    for table in ('om_whatsapp_account_res_users_rel', 'om_whatsapp_account'):
        if sql.table_exists(cr, table):
            cr.execute(f'DROP TABLE "{table}" CASCADE')
    _logger.info("The WhatsApp columns moved to the Social Inbox are dropped")
