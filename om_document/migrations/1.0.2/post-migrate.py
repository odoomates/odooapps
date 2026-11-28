""" Move the document types and the documents of Document Expiry to Documents, which replaces it in this module.

document.type becomes om.documents.type and document.document becomes om.documents.document, with the same values;
the note of a document becomes its description, its first file its file and the other files its extra files. The
chatter, the activities, the followers, the files, the external ids and the references of the other tables follow the
records, before Odoo removes the old models and their data at the end of the upgrade. The maps of the old ids to the
new ones stay until the end script, which restores the dates of the documents and drops the old tables.
"""
import logging

from odoo import SUPERUSER_ID, Command, api
from odoo.tools import SQL, sql

_logger = logging.getLogger(__name__)

OLD_DOCUMENT, NEW_DOCUMENT = 'document.document', 'om.documents.document'
OLD_TYPE, NEW_TYPE = 'document.type', 'om.documents.type'
OLD_TABLES = {'document_document': 'om_documents_document', 'document_type': 'om_documents_type'}

# the fields of document.document kept under another name
RENAMED_FIELDS = {'note': 'description', 'state': 'expiry_state', 'attachment_ids': 'extra_attachment_ids'}
# the actions of Document Expiry and the ones of Documents replacing them
ACTIONS = {
    'om_document.om_document_action': 'om_document.action_expiry_documents',
    'om_document.om_document_action_expiring': 'om_document.action_expiry_expiring',
    'om_document.om_document_action_expired': 'om_document.action_expiry_expired',
    'om_document.om_document_type_action': 'om_document.action_document_types',
}
TYPE_COLUMNS = ['name', 'code', 'sequence', 'active', 'model_id', 'res_model', 'has_number', 'has_issue_date',
                'has_expiry_date', 'reminder_days', 'notify_holder', 'company_id', 'description',
                'create_uid', 'create_date', 'write_uid', 'write_date']


class MigrationError(Exception):
    pass


def _check(label, expected, found):
    if expected != found:
        raise MigrationError('Document Expiry upgrade: %s: %s expected, %s found' % (label, expected, found))


def _relation(cr, model, field):
    cr.execute("SELECT relation_table, column1, column2 FROM ir_model_fields WHERE model = %s AND name = %s",
               [model, field])
    return cr.fetchone()


def _fill_map(cr, table, mapping):
    cr.execute(SQL("DROP TABLE IF EXISTS %s", SQL.identifier(table)))
    cr.execute(SQL("CREATE TABLE %s (old_id integer PRIMARY KEY, new_id integer NOT NULL)", SQL.identifier(table)))
    if mapping:
        cr.execute(SQL("INSERT INTO %s (old_id, new_id) VALUES %s", SQL.identifier(table),
                       SQL(', ').join(SQL('(%s, %s)', old, new) for old, new in mapping.items())))


def _migrate_types(env):
    cr = env.cr
    columns = SQL(', ').join(SQL.identifier(column) for column in TYPE_COLUMNS)
    cr.execute("SELECT id, code, model_id, company_id FROM document_type ORDER BY id")
    type_map = {}
    for type_id, code, model_id, company_id in cr.fetchall():
        # a type already in Documents, with the same code, kind of record and company, is the same type
        if code:
            cr.execute("""SELECT id FROM om_documents_type WHERE code = %s AND model_id IS NOT DISTINCT FROM %s
                          AND company_id IS NOT DISTINCT FROM %s""", [code, model_id, company_id])
            existing = cr.fetchone()
            if existing:
                type_map[type_id] = existing[0]
                continue
        cr.execute(SQL("INSERT INTO om_documents_type (%s) SELECT %s FROM document_type WHERE id = %s RETURNING id",
                       columns, columns, type_id))
        type_map[type_id] = cr.fetchone()[0]
    _fill_map(cr, 'om_document_type_map', type_map)
    table, column1, column2 = _relation(cr, OLD_TYPE, 'user_ids')
    if table and sql.table_exists(cr, table):
        cr.execute(SQL("""INSERT INTO om_documents_type_user_rel (type_id, user_id)
                          SELECT m.new_id, r.%s FROM %s r JOIN om_document_type_map m ON m.old_id = r.%s
                          ON CONFLICT DO NOTHING""",
                       SQL.identifier(column2), SQL.identifier(table), SQL.identifier(column1)))
    env.invalidate_all()
    return type_map


def _migrate_documents(env, type_map):
    """ The documents, created with the ORM for the computed fields, then their dates and authors restored. """
    cr = env.cr
    cr.execute("""SELECT id, name, active, res_model, res_id, type_id, number, date_issue, date_expiry, country_id,
                         last_reminder, previous_id, note, company_id, create_uid, create_date, write_uid,
                         write_date
                  FROM document_document ORDER BY id""")
    rows = cr.dictfetchall()
    table, column1, column2 = _relation(cr, OLD_DOCUMENT, 'attachment_ids')
    files = {}
    if table and sql.table_exists(cr, table):
        cr.execute(SQL("SELECT %s, %s FROM %s ORDER BY %s, %s", SQL.identifier(column1), SQL.identifier(column2),
                       SQL.identifier(table), SQL.identifier(column1), SQL.identifier(column2)))
        for document_id, attachment_id in cr.fetchall():
            files.setdefault(document_id, []).append(attachment_id)

    Document = env[NEW_DOCUMENT].with_context(
        active_test=False, tracking_disable=True, mail_create_nolog=True, mail_create_nosubscribe=True,
        mail_notrack=True, om_documents_no_sync=True)
    Type = env[NEW_TYPE].with_context(active_test=False)
    users = env['res.users'].with_context(active_test=False)
    document_map = {}
    for row in rows:
        doc_type = Type.browse(type_map[row['type_id']])
        company = env['res.company'].browse(row['company_id'])
        record = None
        if row['res_model'] in env and row['res_id']:
            record = env[row['res_model']].browse(row['res_id']).exists() or None
        folder = Document.with_company(company)._get_expiry_folder(doc_type, record) if record \
            else Document._get_expiry_default_folder(company)
        creator = users.browse(row['create_uid']).exists()
        owner = creator if creator and creator.active and not creator.share else folder.owner_id
        document = Document.with_company(company).create({
            'name': row['name'],
            'active': row['active'],
            'folder_id': folder.id,
            'owner_id': owner.id,
            'res_model': row['res_model'],
            'res_id': row['res_id'],
            'type_id': doc_type.id,
            'number': row['number'],
            'date_issue': row['date_issue'],
            'date_expiry': row['date_expiry'],
            'country_id': row['country_id'],
            'last_reminder': row['last_reminder'],
            'description': row['note'],
        })
        document_map[row['id']] = document.id
    env.flush_all()
    _fill_map(cr, 'om_document_document_map', document_map)

    # the files of the documents, and of their chatter, now belong to the new documents
    cr.execute("""UPDATE ir_attachment a SET res_model = %s, res_id = m.new_id
                  FROM om_document_document_map m WHERE a.res_model = %s AND a.res_id = m.old_id""",
               [NEW_DOCUMENT, OLD_DOCUMENT])
    cr.execute("""UPDATE ir_attachment a SET res_model = %s, res_id = m.new_id
                  FROM om_document_type_map m WHERE a.res_model = %s AND a.res_id = m.old_id""",
               [NEW_TYPE, OLD_TYPE])
    env.invalidate_all()
    Attachment = env['ir.attachment'].sudo()
    for old_id, attachment_ids in files.items():
        if old_id not in document_map:
            continue
        document = Document.browse(document_map[old_id])
        attachments = Attachment.browse(attachment_ids).exists()
        if not attachments:
            continue
        main, extra = attachments[0], attachments[1:]
        # a file of another record stays there: the document gets a copy of it
        main = main._om_documents_claim(document)
        document.write({
            'attachment_id': main.id,
            'file_name': main.name,
            'type': 'binary',
            'extra_attachment_ids': [Command.set(extra.ids)],
        })
    env.flush_all()

    env.invalidate_all()
    return document_map


def _link_renewals(cr):
    """ The renewals: the new documents renew the new documents. """
    cr.execute("""UPDATE om_documents_document n SET previous_id = p.new_id
                  FROM document_document o
                  JOIN om_document_document_map m ON m.old_id = o.id
                  JOIN om_document_document_map p ON p.old_id = o.previous_id
                  WHERE n.id = m.new_id""")


def _migrate_mail(cr, new_model_id, old_model_id):
    cr.execute("""UPDATE mail_message t SET model = %s, res_id = m.new_id
                  FROM om_document_document_map m WHERE t.model = %s AND t.res_id = m.old_id""",
               [NEW_DOCUMENT, OLD_DOCUMENT])
    cr.execute("""UPDATE mail_followers t SET res_model = %s, res_id = m.new_id
                  FROM om_document_document_map m WHERE t.res_model = %s AND t.res_id = m.old_id""",
               [NEW_DOCUMENT, OLD_DOCUMENT])
    cr.execute("""UPDATE mail_activity t SET res_model = %s, res_model_id = %s, res_id = m.new_id
                  FROM om_document_document_map m WHERE t.res_model_id = %s AND t.res_id = m.old_id""",
               [NEW_DOCUMENT, new_model_id, old_model_id])
    cr.execute("UPDATE mail_activity_type SET res_model = %s WHERE res_model = %s", [NEW_DOCUMENT, OLD_DOCUMENT])
    if sql.table_exists(cr, 'mail_tracking_value'):
        # the tracked changes of the moved messages show on the fields of the new documents
        cr.execute("""UPDATE mail_tracking_value t SET field_id = nf.id
                      FROM ir_model_fields f, ir_model_fields nf
                      WHERE t.field_id = f.id AND f.model = %s AND nf.model = %s
                        AND nf.name = CASE f.name WHEN 'note' THEN 'description' ELSE f.name END""",
                   [OLD_DOCUMENT, NEW_DOCUMENT])


def _migrate_references(env, model_ids):
    """ The external ids and the references of the other tables to the old records. """
    cr = env.cr
    for old_model, new_model, map_table in [(OLD_DOCUMENT, NEW_DOCUMENT, 'om_document_document_map'),
                                            (OLD_TYPE, NEW_TYPE, 'om_document_type_map')]:
        # the external ids, of any module, e.g. the types of HR Documents: their data updates the moved records
        cr.execute(SQL("""UPDATE ir_model_data d SET model = %s, res_id = m.new_id
                          FROM %s m WHERE d.model = %s AND d.res_id = m.old_id""",
                       new_model, SQL.identifier(map_table), old_model))
        cr.execute("DELETE FROM ir_model_data WHERE model = %s", [old_model])
        cr.execute("UPDATE ir_filters SET model_id = %s WHERE model_id = %s", [new_model, old_model])
        cr.execute("UPDATE ir_model_fields SET relation = %s WHERE relation = %s AND state = 'manual'",
                   [new_model, old_model])

    # the columns of the other tables pointing to the old records, e.g. the documents of the prints
    cr.execute("""SELECT c.conname, src.relname, a.attname, dst.relname, c.confdeltype
                  FROM pg_constraint c
                  JOIN pg_class src ON src.oid = c.conrelid
                  JOIN pg_class dst ON dst.oid = c.confrelid
                  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
                  WHERE c.contype = 'f' AND dst.relname IN %s AND src.relname NOT IN %s""",
               [tuple(OLD_TABLES), tuple(OLD_TABLES)])
    foreign_keys = cr.fetchall()
    ondelete = {'a': 'NO ACTION', 'r': 'RESTRICT', 'c': 'CASCADE', 'n': 'SET NULL', 'd': 'SET DEFAULT'}
    old_relations = {_relation(cr, OLD_DOCUMENT, 'attachment_ids')[0], _relation(cr, OLD_TYPE, 'user_ids')[0]}
    for constraint, table, column, target, action in foreign_keys:
        if table in old_relations:
            continue
        map_table = 'om_document_document_map' if target == 'document_document' else 'om_document_type_map'
        sql.drop_constraint(cr, table, constraint)
        cr.execute(SQL("UPDATE %s t SET %s = m.new_id FROM %s m WHERE t.%s = m.old_id",
                       SQL.identifier(table), SQL.identifier(column), SQL.identifier(map_table),
                       SQL.identifier(column)))
        sql.add_foreign_key(cr, table, column, OLD_TABLES[target], 'id', ondelete[action])
        _logger.info('Document Expiry upgrade: %s.%s now points to %s', table, column, OLD_TABLES[target])

    # the custom fields of the old models move to the new ones, with their values
    for old_model, new_model, old_table, map_table in [
            (OLD_DOCUMENT, NEW_DOCUMENT, 'document_document', 'om_document_document_map'),
            (OLD_TYPE, NEW_TYPE, 'document_type', 'om_document_type_map')]:
        new_table = OLD_TABLES[old_table]
        cr.execute("""SELECT f.id, f.name, f.ttype, f.store, f.relation_table, f.column1 FROM ir_model_fields f
                      WHERE f.model = %s AND f.state = 'manual' AND NOT EXISTS (
                          SELECT 1 FROM ir_model_fields n WHERE n.model = %s AND n.name = f.name)""",
                   [old_model, new_model])
        for field_id, name, ttype, store, relation_table, column1 in cr.fetchall():
            if ttype == 'many2many' and relation_table and sql.table_exists(cr, relation_table):
                cr.execute(SQL("UPDATE %s t SET %s = m.new_id FROM %s m WHERE t.%s = m.old_id",
                               SQL.identifier(relation_table), SQL.identifier(column1), SQL.identifier(map_table),
                               SQL.identifier(column1)))
            elif store and sql.column_exists(cr, old_table, name):
                cr.execute("""SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a
                              WHERE a.attrelid = %s::regclass AND a.attname = %s""", [old_table, name])
                column_type = cr.fetchone()[0]
                if not sql.column_exists(cr, new_table, name):
                    sql.create_column(cr, new_table, name, SQL(column_type))
                cr.execute(SQL("UPDATE %s n SET %s = o.%s FROM %s o, %s m WHERE o.id = m.old_id AND n.id = m.new_id",
                               SQL.identifier(new_table), SQL.identifier(name), SQL.identifier(name),
                               SQL.identifier(old_table), SQL.identifier(map_table)))
            cr.execute("UPDATE ir_model_fields SET model = %s, model_id = %s WHERE id = %s",
                       [new_model, model_ids[new_model], field_id])
            _logger.info('Document Expiry upgrade: custom field %s moved to %s', name, new_model)

    # the actions, scheduled actions and automations on the documents, but the ones of Document Expiry
    own = SQL("""id NOT IN (SELECT res_id FROM ir_model_data WHERE module = 'om_document'
                            AND model IN ('ir.actions.server', 'ir.actions.act_window', 'ir.actions.report'))""")
    for old_model, new_model in [(OLD_DOCUMENT, NEW_DOCUMENT), (OLD_TYPE, NEW_TYPE)]:
        old_id, new_id = model_ids[old_model], model_ids[new_model]
        cr.execute(SQL("UPDATE ir_act_server SET model_id = %s WHERE model_id = %s AND %s", new_id, old_id, own))
        for column in ['crud_model_id', 'update_related_model_id']:
            if sql.column_exists(cr, 'ir_act_server', column):
                cr.execute(SQL("UPDATE ir_act_server SET %s = %s WHERE %s = %s", SQL.identifier(column), new_id,
                               SQL.identifier(column), old_id))
        cr.execute(SQL("UPDATE ir_act_window SET res_model = %s WHERE res_model = %s AND %s", new_model, old_model,
                       own))
        cr.execute(SQL("UPDATE ir_act_report_xml SET model = %s WHERE model = %s AND %s", new_model, old_model, own))
        for table in ['ir_act_server', 'ir_act_window', 'ir_act_report_xml', 'ir_act_client', 'ir_act_url']:
            if sql.column_exists(cr, table, 'binding_model_id'):
                cr.execute(SQL("UPDATE %s SET binding_model_id = %s WHERE binding_model_id = %s AND %s",
                               SQL.identifier(table), new_id, old_id, own))
        if sql.table_exists(cr, 'base_automation'):
            cr.execute("UPDATE base_automation SET model_id = %s WHERE model_id = %s", [new_id, old_id])
        cr.execute("UPDATE mail_template SET model_id = %s, model = %s WHERE model_id = %s",
                   [new_id, new_model, old_id])

    # the saved filters of the old actions open the new ones; their domains use the new field names
    for old_xmlid, new_xmlid in ACTIONS.items():
        old_action = env.ref(old_xmlid, raise_if_not_found=False)
        new_action = env.ref(new_xmlid, raise_if_not_found=False)
        if old_action and new_action:
            cr.execute("UPDATE ir_filters SET action_id = %s WHERE action_id = %s", [new_action.id, old_action.id])
    cr.execute("SELECT id, domain FROM ir_filters WHERE model_id = %s", [NEW_DOCUMENT])
    for filter_id, domain in cr.fetchall():
        new_domain = domain or ''
        for old_name, new_name in RENAMED_FIELDS.items():
            new_domain = new_domain.replace("'%s'" % old_name, "'%s'" % new_name)
        if new_domain != (domain or ''):
            cr.execute("UPDATE ir_filters SET domain = %s WHERE id = %s", [new_domain, filter_id])


def _migrate_groups(env):
    """ The administrators of Document Expiry administer Documents, where the expiring documents are now. """
    old_group = env.ref('om_document.group_document_manager', raise_if_not_found=False)
    new_group = env.ref('om_document.group_documents_manager', raise_if_not_found=False)
    if not old_group or not new_group:
        return
    users = old_group.with_context(active_test=False).user_ids
    if users:
        new_group.write({'user_ids': [Command.link(user.id) for user in users]})
    implying = env['res.groups'].search([('implied_ids', 'in', old_group.ids)]) - old_group
    if implying:
        implying.write({'implied_ids': [Command.link(new_group.id)]})


def _counts(cr):
    def count(query, params=()):
        cr.execute(query, params)
        return cr.fetchone()[0]
    return {
        'types': count("SELECT count(*) FROM document_type"),
        'documents': count("SELECT count(*) FROM document_document"),
        'messages': count("SELECT count(*) FROM mail_message t JOIN document_document o ON o.id = t.res_id "
                          "WHERE t.model = %s", [OLD_DOCUMENT]),
        'followers': count("SELECT count(*) FROM mail_followers t JOIN document_document o ON o.id = t.res_id "
                           "WHERE t.res_model = %s", [OLD_DOCUMENT]),
        'activities': count("SELECT count(*) FROM mail_activity t JOIN document_document o ON o.id = t.res_id "
                            "WHERE t.res_model = %s", [OLD_DOCUMENT]),
        'attachments': count("SELECT count(*) FROM ir_attachment t JOIN document_document o ON o.id = t.res_id "
                             "WHERE t.res_model = %s", [OLD_DOCUMENT]),
        'reminded': count("SELECT count(*) FROM document_document WHERE last_reminder != -1"),
    }


def migrate(cr, version):
    if not sql.table_exists(cr, 'document_document') or not sql.table_exists(cr, 'document_type'):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    model_ids = {model: env['ir.model']._get_id(model) for model in [OLD_DOCUMENT, NEW_DOCUMENT, OLD_TYPE, NEW_TYPE]}
    before = _counts(cr)
    cr.execute("SELECT count(*) FROM om_documents_document")
    documents_before = cr.fetchone()[0]

    type_map = _migrate_types(env)
    document_map = _migrate_documents(env, type_map)
    _migrate_mail(cr, model_ids[NEW_DOCUMENT], model_ids[OLD_DOCUMENT])
    _migrate_references(env, model_ids)
    _migrate_groups(env)
    env.flush_all()
    _link_renewals(cr)
    env.invalidate_all()

    def count(query, params=()):
        cr.execute(query, params)
        return cr.fetchone()[0]
    new_ids = tuple(document_map.values()) or (0,)
    _check('document types', before['types'], len(type_map))
    _check('documents', before['documents'], len(document_map))
    _check('documents in Documents', documents_before + len(document_map),
           count("SELECT count(*) FROM om_documents_document"))
    _check('messages', before['messages'],
           count("SELECT count(*) FROM mail_message WHERE model = %s AND res_id IN %s", [NEW_DOCUMENT, new_ids]))
    _check('followers', before['followers'],
           count("SELECT count(*) FROM mail_followers WHERE res_model = %s AND res_id IN %s",
                 [NEW_DOCUMENT, new_ids]))
    _check('activities', before['activities'],
           count("SELECT count(*) FROM mail_activity WHERE res_model = %s AND res_id IN %s",
                 [NEW_DOCUMENT, new_ids]))
    _check('reminders sent', before['reminded'],
           count("SELECT count(*) FROM om_documents_document WHERE id IN %s AND last_reminder != -1", [new_ids]))
    # a file of another record is copied: the moved files are at least as many as before
    moved_files = count("SELECT count(*) FROM ir_attachment WHERE res_model = %s AND res_id IN %s",
                        [NEW_DOCUMENT, new_ids])
    if moved_files < before['attachments']:
        _check('files', before['attachments'], moved_files)
    _logger.info('Document Expiry upgrade: %s document types and %s documents moved to Documents, with %s files, '
                 '%s messages and %s activities', len(type_map), len(document_map), moved_files,
                 before['messages'], before['activities'])
