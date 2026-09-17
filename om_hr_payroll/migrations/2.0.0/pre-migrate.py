import logging

_logger = logging.getLogger(__name__)

MODULE = 'om_hr_payroll'

# The country specific example data of 1.x, dropped in 2.0.0. The records themselves are only removed when the
# database never used them: the ones in use are detached from the module and kept as data of the user.
LEGACY_RULES = ('hr_rule_hra', 'hr_rule_da', 'hr_rule_travel', 'hr_rule_meal', 'hr_rule_medical')
LEGACY_CATEGORIES = ('HRA', 'DA', 'Travel', 'Meal', 'Medical', 'Other')


def _xmlid_records(cr, names, model):
    """ :return: {xml id: database id} of the records of `model` still owned by the module """
    cr.execute("""
        SELECT name, res_id
          FROM ir_model_data
         WHERE module = %s AND model = %s AND name IN %s
    """, [MODULE, model, tuple(names)])
    return dict(cr.fetchall())


def _detach(cr, names, model, reason):
    """ Give up the ownership of the records: the update of the module no longer deletes them. """
    if not names:
        return
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module = %s AND model = %s AND name IN %s
    """, [MODULE, model, tuple(names)])
    _logger.info('om_hr_payroll: kept %s %s(s) %s: %s', len(names), model, reason, ', '.join(sorted(names)))


def migrate(cr, version):
    """ Upgrade to 2.0.0: the allowances of the contract become salary components.

    The example rules and the categories of the allowances are country specific and leave the module. This
    script runs before the data of the module is reloaded, and decides for each of those records whether the
    upgrade may delete it:

    * a rule used by a salary structure or by a payslip, and a category used by a rule or by a payslip line,
      are detached from the module and stay in the database, so that the payslips already computed keep their
      meaning and the structures of the customer keep working
    * the records nothing refers to are left to the upgrade, which deletes them

    The values of the allowance fields are moved to the salary components by post-migrate.py.
    """
    if not version:
        return

    # rules of the module still referred to by a structure or by a payslip line
    rules = _xmlid_records(cr, LEGACY_RULES, 'hr.salary.rule')
    if rules:
        cr.execute("""
            SELECT DISTINCT rule_id
              FROM hr_structure_salary_rule_rel
             WHERE rule_id IN %s
        """, [tuple(rules.values())])
        used_ids = {row[0] for row in cr.fetchall()}
        cr.execute("""
            SELECT DISTINCT salary_rule_id
              FROM hr_payslip_line
             WHERE salary_rule_id IN %s
        """, [tuple(rules.values())])
        used_ids |= {row[0] for row in cr.fetchall()}
        _detach(cr, [name for name, res_id in rules.items() if res_id in used_ids],
                'hr.salary.rule', 'used by a structure or a payslip')

    # categories of the module still referred to by a rule, a component or a payslip line
    categories = _xmlid_records(cr, LEGACY_CATEGORIES, 'hr.salary.rule.category')
    if categories:
        ids = tuple(categories.values())
        used_ids = set()
        for table in ('hr_salary_rule', 'hr_payslip_line'):
            cr.execute(f"""
                SELECT DISTINCT category_id
                  FROM {table}
                 WHERE category_id IN %s
            """, [ids])
            used_ids |= {row[0] for row in cr.fetchall()}
        cr.execute("""
            SELECT DISTINCT parent_id
              FROM hr_salary_rule_category
             WHERE parent_id IN %s
        """, [ids])
        used_ids |= {row[0] for row in cr.fetchall()}
        _detach(cr, [name for name, res_id in categories.items() if res_id in used_ids],
                'hr.salary.rule.category', 'used by a rule or a payslip')
