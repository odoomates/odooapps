# Under the hood: what a step made in the database, read from PostgreSQL
# itself. The tables of the models the step creates or changes, with their
# real columns, rows and links, and the SQL that made them; and the records of
# Odoo's own tables the step's files load: access rights, actions, menus,
# views, reports, groups, the module. Read only, a few rows at a time.
from odoo.tools import SQL
from odoo.tools.translate import LazyTranslate

from .course_files import csv_accesses, files_at, models_at, xml_records

_lt = LazyTranslate(__name__)

ROWS = 5
SQL_TYPES = {'char': 'varchar', 'text': 'text', 'date': 'date', 'integer': 'int4', 'boolean': 'bool',
             'selection': 'varchar', 'many2one': 'int4', 'float': 'numeric'}
# the records of Odoo's own tables a step's files load, and what to show of them
META = {
    'ir.access': ('ir_access', ['name', 'group_id', 'operation', 'domain']),
    'ir.actions.act_window': ('ir_act_window', ['name', 'res_model', 'view_mode']),
    'ir.ui.menu': ('ir_ui_menu', ['complete_name', 'action']),
    'ir.ui.view': ('ir_ui_view', ['name', 'type', 'model', 'inherit_id']),
    'ir.actions.report': ('ir_act_report_xml', ['name', 'model', 'report_type', 'report_name']),
    'report.paperformat': ('report_paperformat', ['name', 'format', 'orientation']),
    'res.groups': ('res_groups', ['name', 'privilege_id']),
    'res.groups.privilege': ('res_groups_privilege', ['name']),
}


def value(record, name):
    raw = record[name]
    if hasattr(raw, '_name'):
        return raw.display_name or False
    return raw


class Hood:

    def __init__(self, progress, course, index):
        self.progress = progress
        self.env = progress.env
        self.course = course
        self.index = index
        self.step = course['steps'][index]
        self.live = progress.mode == 'live'
        self.builder = progress._live() if self.live else None

    #
    # the step's models: their tables
    #

    def model_name(self, model):
        return self.builder.model_name(model) if self.live else model

    def field_name(self, model, name):
        if self.live and not name.startswith('x_'):
            return 'x_' + name
        return name

    def step_models(self):
        """ The models the step creates or changes, in the order it names them. """
        models = []
        for op in self.step.get('live') or ():
            if op.get('model') and op['model'] not in models:
                models.append(op['model'])
        for _path, record in xml_records(files_at(self.course, self.index), paths=set(self.step.get('files') or ())):
            if record['model'] in self.builder_models() and record['model'] not in models:
                models.append(record['model'])
        for extra in self.step.get('checks') or ():
            if extra.get('model') and extra['model'] not in models:
                models.append(extra['model'])
        return models

    def builder_models(self):
        return set(models_at(self.course, len(self.course['steps']) - 1))

    def tables(self):
        models = models_at(self.course, self.index)
        before = models_at(self.course, self.index - 1) if self.index else {}
        result = []
        for model in self.step_models():
            spec = models.get(model)
            if not spec:
                continue
            result.append(self.table(model, spec, before.get(model)))
            # the tables the new links point to
            for field in spec['fields'].values():
                if field['type'] == 'many2one' and field['name'] not in (before.get(model) or {}).get('fields', {}):
                    target = models.get(field['relation'])
                    if target and field['relation'] not in self.step_models():
                        result.append(self.table(field['relation'], target, target))
        return result

    def table(self, model, spec, before):
        """ A table: the SQL that made it, its real columns, its last rows. """
        name = self.model_name(model)
        Model = self.env[name] if name in self.env else None
        new_fields = [field for field in spec['fields'] if field not in (before or {}).get('fields', {})]
        existing = bool(spec.get('existing'))
        table_name = Model._table if Model is not None else name.replace('.', '_')
        columns = []
        for field_name, field in spec['fields'].items():
            column = self.field_name(model, field_name)
            stored = not field.get('compute')
            columns.append({
                'name': column, 'type': SQL_TYPES.get(field['type'], field['type']), 'stored': stored,
                'new': field_name in new_fields,
                'link': ('%s.id' % self.env[self.model_name(field['relation'])]._table
                         if field['type'] == 'many2one' and self.model_name(field['relation']) in self.env else False),
            })
        sql = self.sql(table_name, columns, new_fields, existing or before is not None)
        result = {'kind': 'table', 'model': name, 'table': table_name, 'sql': sql, 'exists': False,
                  'columns': [{'name': 'id', 'type': 'serial', 'stored': True, 'new': False, 'link': False}] + columns,
                  'rows': [], 'count': 0}
        if Model is None or not self._table_exists(table_name):
            return result
        real = self._columns(table_name)
        for column in result['columns']:
            column['exists'] = column['name'] in real
        shown = [column['name'] for column in result['columns'] if column.get('exists')]
        self.env.cr.execute(SQL('SELECT COUNT(*) FROM %s', SQL.identifier(table_name)))
        result['count'] = self.env.cr.fetchone()[0]
        self.env.cr.execute(SQL('SELECT %s FROM %s ORDER BY id DESC LIMIT %s',
                                SQL(', ').join(SQL.identifier(column) for column in shown),
                                SQL.identifier(table_name), ROWS))
        result['rows'] = [[self._cell(cell) for cell in row] for row in self.env.cr.fetchall()]
        result['shown'] = shown
        result['exists'] = True
        return result

    def sql(self, table, columns, new_fields, altered):
        """ The SQL Odoo runs, in short: CREATE TABLE, or ALTER TABLE for new columns. """
        lines = []
        stored = [column for column in columns if column['stored']]
        if not altered:
            body = ',\n'.join(['    id SERIAL PRIMARY KEY'] + [
                '    %s %s%s' % (column['name'], column['type'].upper(),
                                 ' REFERENCES %s' % column['link'].split('.')[0] if column['link'] else '')
                for column in stored])
            lines.append('CREATE TABLE %s (\n%s\n);' % (table, body))
        else:
            for column in stored:
                if column['new']:
                    lines.append('ALTER TABLE %s ADD COLUMN %s %s%s;' % (
                        table, column['name'], column['type'].upper(),
                        ' REFERENCES %s' % column['link'].split('.')[0] if column['link'] else ''))
        for column in columns:
            if column['new'] and not column['stored']:
                lines.append('-- %s: no column. Computed when read, never stored.' % column['name'])
        return '\n'.join(lines)

    def _table_exists(self, table):
        self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s", [table])
        return bool(self.env.cr.fetchone())

    def _columns(self, table):
        self.env.cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", [table])
        return {row[0] for row in self.env.cr.fetchall()}

    def _cell(self, cell):
        if cell is None or cell is False:
            return None
        if isinstance(cell, dict):  # a translated column: the English value
            return cell.get('en_US') or next(iter(cell.values()), None)
        text = str(cell)
        return text if len(text) <= 40 else text[:37] + '...'

    #
    # the records of Odoo's own tables the step's files load
    #

    def resolve(self, xmlid):
        if self.live:
            return self.builder.record(xmlid)
        return self.env.ref('%s.%s' % (self.course['module'], xmlid), raise_if_not_found=False)

    def records(self):
        files = self.step.get('files') or {}
        found = {}
        for access in csv_accesses(files_at(self.course, self.index)) if any(
                path.endswith('ir.access.csv') for path in files) else ():
            record = self.resolve(access['xmlid'])
            if record:
                found.setdefault('ir.access', []).append(record)
        for _path, record in xml_records(files_at(self.course, self.index), paths=set(files)):
            model = 'ir.ui.view' if record.get('template') else record['model']
            if model in META:
                found_record = self.resolve(record['xmlid'])
                if found_record:
                    found.setdefault(model, []).append(found_record)
        result = []
        for model, records in found.items():
            table, names = META[model]
            result.append({'kind': 'records', 'table': table, 'columns': names,
                           'rows': [[self._cell(value(record, name)) for name in names] for record in records]})
        if 'module' == self.step.get('see'):
            module = self.env['ir.module.module'].sudo().search([('name', '=', self.course['module'])], limit=1)
            if module:
                names = ['name', 'shortdesc', 'author', 'state']
                result.append({'kind': 'records', 'table': 'ir_module_module', 'columns': names,
                               'rows': [[self._cell(value(module, name)) for name in names]]})
        return result

    def messages(self):
        """ The chatter: the messages of the records of the step's models (Odoo 20 keeps
        what tracking noted in the message itself). """
        if not any(op['op'] in ('mail_thread', 'tracking') for op in self.step.get('live') or ()) \
                or 'mail.message' not in self.env:
            return []
        model = self.model_name(self.step_models()[0])
        messages = self.env['mail.message'].sudo().search([('model', '=', model)], order='id desc', limit=ROWS)
        result = [{'kind': 'records', 'table': 'mail_message', 'columns': ['res_id', 'message_type', 'body'],
                   'rows': [[message.res_id, message.message_type, self._cell(message.preview or '')]
                            for message in messages]}]
        return result

    def build(self):
        return {'tables': self.tables(), 'records': self.records() + self.messages()}
