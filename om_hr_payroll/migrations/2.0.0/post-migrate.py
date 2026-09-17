import logging
import re

from psycopg2.extras import execute_values

from odoo import api, fields, SUPERUSER_ID
from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)

# 1.x field of hr.version -> (code, name of the salary component it becomes)
LEGACY_FIELDS = {
    'hra': ('HRA', 'House Rent Allowance'),
    'da': ('DA', 'Dearness Allowance'),
    'travel_allowance': ('TRAVEL', 'Travel Allowance'),
    'meal_allowance': ('MEAL', 'Meal Allowance'),
    'medical_allowance': ('MEDICAL', 'Medical Allowance'),
    'other_allowance': ('OTHER', 'Other Allowance'),
}

# `contract.hra`, and `employee.contract_id.hra` with whatever leads to it, become `components.HRA`
CODE_FIELDS = '|'.join(LEGACY_FIELDS)
CODE_PATTERN = re.compile(rf'\b(?:[A-Za-z_]\w*\.)*contract(?:_id)?\.({CODE_FIELDS})\b')

CODE_COLUMNS = ('amount_python_compute', 'condition_python')


def _create_components(cr, env):
    """ Move the amounts of the allowance fields onto the versions as salary components.

    :return: the number of amounts moved
    """
    allowance = env.ref('om_hr_payroll.ALW', raise_if_not_found=False)
    now = fields.Datetime.now()
    moved = 0
    for field, (code, name) in LEGACY_FIELDS.items():
        if not column_exists(cr, 'hr_version', field):
            continue
        cr.execute(f'SELECT id, {field} FROM hr_version WHERE {field} IS NOT NULL AND {field} != 0')
        amounts = cr.fetchall()
        if not amounts:
            continue
        component = env['hr.salary.component'].search([('code', '=', code)], limit=1)
        if not component:
            component = env['hr.salary.component'].create({
                'name': name,
                'code': code,
                'category_id': allowance.id if allowance else False,
                'company_id': False,
            })
        # the versions that already carry the component are left alone, so that the script can be run again
        execute_values(cr._obj, """
            INSERT INTO hr_version_salary_component
                        (version_id, component_id, amount, code, sequence, create_uid, create_date,
                         write_uid, write_date)
                 VALUES %s
            ON CONFLICT (version_id, component_id) DO NOTHING
        """, [(version_id, component.id, amount, code, component.sequence,
               SUPERUSER_ID, now, SUPERUSER_ID, now)
              for version_id, amount in amounts])
        moved += len(amounts)
        _logger.info('om_hr_payroll: %s amount(s) of %s moved to the salary component %s',
                     len(amounts), field, code)
    return moved


def _rewrite_rules(cr, env):
    """ Point the code of the salary rules at the salary components instead of the fields of the contract.

    :return: the number of rules rewritten
    """
    rules = env['hr.salary.rule'].search([])
    rewritten = env['hr.salary.rule']
    for rule in rules:
        values = {}
        for column in CODE_COLUMNS:
            code = rule[column]
            if code and CODE_PATTERN.search(code):
                values[column] = CODE_PATTERN.sub(
                    lambda match: 'components.%s' % LEGACY_FIELDS[match.group(1)][0], code)
        if values:
            note = rule.note or ''
            values['note'] = (note + '\n\n' if note else '') + (
                'Upgrade to 2.0.0: the allowances of the contract became salary components. '
                'The code of the rule before the upgrade was:\n\n'
                + '\n\n'.join('%s:\n%s' % (column, rule[column]) for column in CODE_COLUMNS if rule[column]))
            rule.write(values)
            rewritten |= rule
    if rewritten:
        _logger.info('om_hr_payroll: %s salary rule(s) now read the salary components: %s',
                     len(rewritten), ', '.join(rewritten.mapped('code')))
    return len(rewritten)


def migrate(cr, version):
    """ Upgrade to 2.0.0: the allowances of the contract become salary components.

    The fields hra, da, travel_allowance, meal_allowance, medical_allowance and other_allowance of the version
    are replaced by the salary components, which every company describes itself. This script:

    * creates a salary component for each allowance field holding an amount somewhere
    * copies the amount of every version onto it
    * rewrites the salary rules reading `contract.hra` and the like into `components.HRA`, keeping their
      former code in the note of the rule

    The columns of the former fields are left in the table: check the result of the upgrade before dropping
    them, nothing reads them any more.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    moved = _create_components(cr, env)
    rewritten = _rewrite_rules(cr, env)
    if moved or rewritten:
        _logger.info(
            'om_hr_payroll: upgrade to 2.0.0 done, %s allowance amount(s) and %s salary rule(s) migrated. '
            'The columns %s of hr_version are no longer used and may be dropped once the result is checked. '
            'The salary structures are left as they are: the Allowances and the Deductions rules of 2.0.0, '
            'which pay every salary component of their category, are only added to the structures created '
            'from now on, so that nothing is paid twice.',
            moved, rewritten, ', '.join(LEGACY_FIELDS))
