import logging

from odoo.tools import SQL
from odoo.tools.sql import rename_column, table_columns

_logger = logging.getLogger(__name__)

# The accounts of the salary rules are set per company: the value of a rule is kept for the companies that can use
# it (the companies of the account and their branches), and only for the company of the rule when it has one.
COLUMNS = {
    'account_debit': SQL("""
        SELECT res_company_id AS company_id FROM account_account_res_company_rel
         WHERE account_account_id = r.old_value"""),
    'account_credit': SQL("""
        SELECT res_company_id AS company_id FROM account_account_res_company_rel
         WHERE account_account_id = r.old_value"""),
    'account_tax_id': SQL("SELECT company_id FROM account_tax WHERE id = r.old_value"),
    # an analytic account without company is shared by all the companies
    'analytic_account_id': SQL("""
        SELECT COALESCE(a.company_id, c.id) AS company_id
          FROM account_analytic_account a, res_company c
         WHERE a.id = r.old_value AND (a.company_id IS NULL OR a.company_id = c.id)"""),
}


def migrate(cr, version):
    # this script runs on every update: only the columns not converted yet are handled
    columns = table_columns(cr, 'hr_salary_rule')
    for column, owners in COLUMNS.items():
        if column not in columns or columns[column]['udt_name'] == 'jsonb':
            continue
        old_column = f'{column}_before_company_dependent'
        rename_column(cr, 'hr_salary_rule', column, old_column)
        cr.execute(SQL("ALTER TABLE hr_salary_rule ADD COLUMN %s jsonb", SQL.identifier(column)))
        cr.execute(SQL(
            """
            WITH r AS (
                SELECT id, company_id AS rule_company_id, %(old_column)s AS old_value
                  FROM hr_salary_rule
                 WHERE %(old_column)s IS NOT NULL
            ), vals AS (
                SELECT r.id, jsonb_object_agg(c.id::varchar, r.old_value) AS value
                  FROM r
                  JOIN LATERAL (%(owners)s) o ON TRUE
                  JOIN res_company owner ON owner.id = o.company_id
                  JOIN res_company c ON c.parent_path LIKE owner.parent_path || '%%'
                 WHERE r.rule_company_id IS NULL OR r.rule_company_id = c.id
              GROUP BY r.id
            )
            UPDATE hr_salary_rule rule
               SET %(column)s = vals.value
              FROM vals
             WHERE vals.id = rule.id
            """,
            column=SQL.identifier(column), old_column=SQL.identifier(old_column), owners=owners,
        ))
        _logger.info("hr_salary_rule.%s: the values of %s salary rules are now set per company", column, cr.rowcount)
        cr.execute(SQL("ALTER TABLE hr_salary_rule DROP COLUMN %s CASCADE", SQL.identifier(old_column)))
