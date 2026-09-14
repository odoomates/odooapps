""" Upgrade to 2.0.0: rename the legacy models and fields of the module.

    crossovered.budget         -> account.budget
    crossovered.budget.lines   -> account.budget.line
    account.budget.post        -> account.budget.position

Everything referring to the former names is renamed in place (tables, columns, indexes,
model and field metadata, external ids, chatter, attachments, filters...) so that the
records keep their ids, their history and their customizations.
"""
from psycopg2 import sql

from odoo.tools.sql import column_exists, table_exists

MODULE = 'om_account_budget'

# old model -> new model
MODELS = {
    'crossovered.budget': 'account.budget',
    'crossovered.budget.lines': 'account.budget.line',
    'account.budget.post': 'account.budget.position',
}

# model (new name) -> {old field: new field}
FIELDS = {
    'account.budget': {'crossovered_budget_line': 'line_ids'},
    'account.budget.line': {
        'crossovered_budget_id': 'budget_id',
        'general_budget_id': 'position_id',
        'crossovered_budget_state': 'budget_state',
        'theoritical_amount': 'theoretical_amount',
        'percentage': 'achievement',
        'paid_date': 'planned_date',
    },
    'account.analytic.account': {'crossovered_budget_line': 'budget_line_ids'},
}

# many2many table of the budgetary positions
M2M_TABLE = ('account_budget_rel', 'account_budget_position_account_rel')
M2M_COLUMNS = {'budget_id': 'position_id'}

# external ids of the module: old name -> new name
XMLIDS = {
    'view_budget_post_search': 'view_account_budget_position_search',
    'view_budget_post_tree': 'view_account_budget_position_list',
    'view_budget_post_form': 'view_account_budget_position_form',
    'open_budget_post_form': 'action_account_budget_position',
    'menu_budget_post_form': 'menu_account_budget_position',
    'crossovered_budget_view_form': 'view_account_budget_form',
    'crossovered_budget_view_tree': 'view_account_budget_list',
    'view_crossovered_budget_kanban': 'view_account_budget_kanban',
    'view_crossovered_budget_search': 'view_account_budget_search',
    'act_crossovered_budget_view': 'action_account_budget',
    'menu_act_crossovered_budget_view': 'menu_account_budget',
    'view_crossovered_budget_line_search': 'view_account_budget_line_search',
    'view_crossovered_budget_line_tree': 'view_account_budget_line_list',
    'view_crossovered_budget_line_form': 'view_account_budget_line_form',
    'view_crossovered_budget_line_pivot': 'view_account_budget_line_pivot',
    'view_crossovered_budget_line_graph': 'view_account_budget_line_graph',
    'act_crossovered_budget_lines_view': 'action_account_budget_line_analysis',
    'menu_act_crossovered_budget_lines_view': 'menu_account_budget_line_analysis',
    'act_account_analytic_account_cb_lines': 'action_analytic_account_budget_lines',
    'access_crossovered_budget_accountant': 'access_account_budget_accountant',
    'budget_comp_rule': 'account_budget_company_rule',
    'access_account_budget_post_accountant': 'access_account_budget_position_accountant',
    'budget_post_comp_rule': 'account_budget_position_company_rule',
    'access_crossovered_budget_lines_accountant': 'access_account_budget_line_accountant',
    'budget_lines_comp_rule': 'account_budget_line_company_rule',
    'crossovered_budget_budgetoptimistic0': 'account_budget_demo_optimistic',
    'crossovered_budget_budgetpessimistic0': 'account_budget_demo_pessimistic',
}

# (table, column) storing a model name as text
MODEL_NAME_COLUMNS = [
    ('mail_message', 'model'),
    ('mail_followers', 'res_model'),
    ('mail_activity', 'res_model'),
    ('mail_template', 'model'),
    ('ir_attachment', 'res_model'),
    ('ir_filters', 'model_id'),
    ('ir_ui_view', 'model'),
    ('ir_act_window', 'res_model'),
    ('ir_act_server', 'model_name'),
    ('ir_act_report_xml', 'model'),
    ('ir_exports', 'resource'),
    ('ir_model_data', 'model'),
    ('ir_model_fields', 'model'),
    ('ir_model_fields', 'relation'),
    ('rating_rating', 'res_model'),
]


def _table(model):
    return model.replace('.', '_')


def _is_text_column(cr, table, column):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s AND data_type IN ('character varying', 'text')
    """, [table, column])
    return bool(cr.fetchone())


def _execute(cr, query, params=None):
    cr.execute(query, params)
    return cr.rowcount


def _rename_table(cr, old, new):
    if not table_exists(cr, old) or table_exists(cr, new):
        return
    cr.execute(sql.SQL('ALTER TABLE {} RENAME TO {}').format(sql.Identifier(old), sql.Identifier(new)))
    cr.execute("SELECT to_regclass(%s)", [f'{old}_id_seq'])
    if cr.fetchone()[0]:
        cr.execute(sql.SQL('ALTER SEQUENCE {} RENAME TO {}').format(
            sql.Identifier(f'{old}_id_seq'), sql.Identifier(f'{new}_id_seq')))


def _rename_indexes(cr, table, old_prefix, column_renames):
    """ Give the indexes of `table` the names the ORM expects, so it does not create them twice. """
    cr.execute("SELECT indexname FROM pg_indexes WHERE tablename = %s", [table])
    for (index,) in cr.fetchall():
        new_index = index
        if new_index.startswith(old_prefix + '_'):
            new_index = table + new_index[len(old_prefix):]
        for old_column, new_column in column_renames.items():
            new_index = new_index.replace(f'__{old_column}_', f'__{new_column}_')
        if new_index != index:
            cr.execute("SELECT to_regclass(%s)", [new_index])
            if not cr.fetchone()[0]:
                cr.execute(sql.SQL('ALTER INDEX {} RENAME TO {}').format(sql.Identifier(index), sql.Identifier(new_index)))


def _rename_models(cr):
    for old_model, new_model in MODELS.items():
        old_table, new_table = _table(old_model), _table(new_model)
        _rename_table(cr, old_table, new_table)
        column_renames = {}
        for old_field, new_field in FIELDS.get(new_model, {}).items():
            if column_exists(cr, new_table, old_field) and not column_exists(cr, new_table, new_field):
                cr.execute(sql.SQL('ALTER TABLE {} RENAME COLUMN {} TO {}').format(
                    sql.Identifier(new_table), sql.Identifier(old_field), sql.Identifier(new_field)))
                column_renames[old_field] = new_field
        if table_exists(cr, new_table):
            _rename_indexes(cr, new_table, old_table, column_renames)

        _execute(cr, "UPDATE ir_model SET model = %s WHERE model = %s", [new_model, old_model])
        for table, column in MODEL_NAME_COLUMNS:
            if _is_text_column(cr, table, column):
                cr.execute(sql.SQL('UPDATE {} SET {} = %s WHERE {} = %s').format(
                    sql.Identifier(table), sql.Identifier(column), sql.Identifier(column)), [new_model, old_model])

        # external ids of the model, its fields and their selection values
        old_key, new_key = old_table, new_table
        _execute(cr, """
            UPDATE ir_model_data
               SET name = regexp_replace(name, %s, %s)
             WHERE module = %s AND model IN ('ir.model', 'ir.model.fields', 'ir.model.fields.selection', 'ir.model.constraint')
               AND name ~ %s
        """, [f'^(model_|field_|selection__|constraint_){old_key}(__|$)', f'\\1{new_key}\\2', MODULE,
              f'^(model_|field_|selection__|constraint_){old_key}(__|$)'])


def _rename_fields(cr):
    for model, renames in FIELDS.items():
        model_key = _table(model)
        for old_field, new_field in renames.items():
            cr.execute("SELECT 1 FROM ir_model_fields WHERE model = %s AND name = %s", [model, new_field])
            if cr.fetchone():
                continue
            _execute(cr, "UPDATE ir_model_fields SET name = %s WHERE model = %s AND name = %s", [new_field, model, old_field])
            _execute(cr, "UPDATE ir_model_fields SET relation_field = %s WHERE relation = %s AND relation_field = %s",
                     [new_field, model, old_field])
            _execute(cr, """
                UPDATE ir_model_data SET name = %s
                 WHERE module = %s AND model = 'ir.model.fields' AND name = %s
            """, [f'field_{model_key}__{new_field}', MODULE, f'field_{model_key}__{old_field}'])
            _execute(cr, """
                UPDATE ir_model_data SET name = regexp_replace(name, %s, %s)
                 WHERE module = %s AND model = 'ir.model.fields.selection' AND name ~ %s
            """, [f'^selection__{model_key}__{old_field}__', f'selection__{model_key}__{new_field}__', MODULE,
                  f'^selection__{model_key}__{old_field}__'])
            # saved filters and actions of the budget models refer to the field names
            for table, column, model_column in (('ir_filters', 'domain', 'model_id'), ('ir_filters', 'context', 'model_id'),
                                                ('ir_filters', 'sort', 'model_id'), ('ir_act_window', 'domain', 'res_model'),
                                                ('ir_act_window', 'context', 'res_model')):
                if column_exists(cr, table, column):
                    cr.execute(sql.SQL("""
                        UPDATE {table} SET {column} = regexp_replace({column}::text, %s, %s, 'g')
                         WHERE {model_column} = ANY(%s) AND {column}::text ~ %s
                    """).format(table=sql.Identifier(table), column=sql.Identifier(column),
                                model_column=sql.Identifier(model_column)),
                        [rf'\m{old_field}\M', new_field, list(FIELDS), rf'\m{old_field}\M'])
            if column_exists(cr, 'ir_exports_line', 'name'):
                _execute(cr, """
                    UPDATE ir_exports_line line SET name = regexp_replace(line.name, %s, %s)
                      FROM ir_exports export
                     WHERE export.id = line.export_id AND export.resource = %s AND line.name ~ %s
                """, [rf'^{old_field}(/|$)', rf'{new_field}\1', model, rf'^{old_field}(/|$)'])


def _rename_m2m(cr):
    old_table, new_table = M2M_TABLE
    if table_exists(cr, old_table) and not table_exists(cr, new_table):
        cr.execute(sql.SQL('ALTER TABLE {} RENAME TO {}').format(sql.Identifier(old_table), sql.Identifier(new_table)))
        for old_column, new_column in M2M_COLUMNS.items():
            if column_exists(cr, new_table, old_column):
                cr.execute(sql.SQL('ALTER TABLE {} RENAME COLUMN {} TO {}').format(
                    sql.Identifier(new_table), sql.Identifier(old_column), sql.Identifier(new_column)))
        _rename_indexes(cr, new_table, old_table, M2M_COLUMNS)
    _execute(cr, "UPDATE ir_model_relation SET name = %s WHERE name = %s", [new_table, old_table])
    _execute(cr, """
        UPDATE ir_model_fields SET relation_table = %s, column1 = 'position_id'
         WHERE relation_table = %s
    """, [new_table, old_table])


def _rename_xmlids(cr):
    for old_name, new_name in XMLIDS.items():
        cr.execute("SELECT 1 FROM ir_model_data WHERE module = %s AND name = %s", [MODULE, new_name])
        if not cr.fetchone():
            _execute(cr, "UPDATE ir_model_data SET name = %s WHERE module = %s AND name = %s", [new_name, MODULE, old_name])


def migrate(cr, version):
    if not version:
        return
    _rename_models(cr)
    _rename_fields(cr)
    _rename_m2m(cr)
    _rename_xmlids(cr)
