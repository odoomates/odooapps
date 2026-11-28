""" Once every module is loaded: the dates and authors of the moved documents as they were, then the old tables and
the group of Document Expiry dropped (see the post script). Odoo removes the old models, views and menus after it. """
import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL, sql

_logger = logging.getLogger(__name__)

TABLES = ['document_document', 'document_type']
MAPS = ['om_document_document_map', 'om_document_type_map']


def migrate(cr, version):
    if not sql.table_exists(cr, 'document_document'):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.flush_all()
    # last: the loading of the other modules writes on the documents, e.g. their new computed fields
    if sql.table_exists(cr, 'om_document_document_map'):
        cr.execute("""UPDATE om_documents_document n
                      SET create_uid = o.create_uid, create_date = o.create_date, write_uid = o.write_uid,
                          write_date = o.write_date
                      FROM document_document o JOIN om_document_document_map m ON m.old_id = o.id
                      WHERE n.id = m.new_id""")
    if sql.table_exists(cr, 'om_document_type_map'):
        cr.execute("""UPDATE om_documents_type n SET write_uid = o.write_uid, write_date = o.write_date
                      FROM document_type o JOIN om_document_type_map m ON m.old_id = o.id
                      WHERE n.id = m.new_id""")
    env.invalidate_all()

    # its users administer Documents now (see the post script)
    for xmlid in ['om_document.group_document_manager', 'om_document.privilege_document']:
        record = env.ref(xmlid, raise_if_not_found=False)
        if record:
            record.unlink()

    cr.execute("""SELECT relation_table FROM ir_model_fields
                  WHERE model IN ('document.document', 'document.type') AND ttype = 'many2many'
                    AND relation_table IS NOT NULL""")
    relations = [table for (table,) in cr.fetchall() if sql.table_exists(cr, table)]
    for table in relations + TABLES + MAPS:
        if sql.table_exists(cr, table):
            cr.execute(SQL("DROP TABLE %s CASCADE", SQL.identifier(table)))
    _logger.info('Document Expiry upgrade: dropped the tables %s', ', '.join(relations + TABLES))
