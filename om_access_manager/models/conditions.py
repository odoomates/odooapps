# Conditions of rules, written as Odoo view conditions (state == 'done',
# amount_total > 1000 and not is_company). The views use them as they are; the
# server needs them as domains, so the supported subset is parsed here and
# anything else is refused when the rule is saved.
import ast

from odoo.tools.translate import _lt

OPERATORS = {
    ast.Eq: '=', ast.NotEq: '!=', ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>=',
    ast.In: 'in', ast.NotIn: 'not in',
}
CONSTANTS = {'True': True, 'False': False, 'None': False}


class ConditionError(ValueError):
    """ Its message is a lazy translation: str(error.args[0]). """


def _parse(expression):
    try:
        return ast.parse((expression or '').strip(), mode='eval').body
    except SyntaxError as error:
        raise ConditionError(_lt("The condition is not valid: %s", error.msg)) from error


def condition_fields(expression):
    """ The field names a condition reads. """
    return {node.id for node in ast.walk(_parse(expression))
            if isinstance(node, ast.Name) and node.id not in CONSTANTS and node.id != 'uid'}


def _value(node, uid):
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
        return False if node.value is None else node.value
    if isinstance(node, ast.Name) and node.id in CONSTANTS:
        return CONSTANTS[node.id]
    if isinstance(node, ast.Name) and node.id == 'uid':
        return uid
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        return -node.operand.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_value(item, uid) for item in node.elts]
    raise ConditionError(_lt("Only fixed values can be compared in a condition."))


def _domain(node, model, uid):
    if isinstance(node, ast.BoolOp):
        operator = '&' if isinstance(node.op, ast.And) else '|'
        parts = [_domain(value, model, uid) for value in node.values]
        return [operator] * (len(parts) - 1) + [term for part in parts for term in part]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return ['!'] + _domain(node.operand, model, uid)
    if isinstance(node, ast.Name) and node.id not in CONSTANTS and node.id != 'uid':
        _field(model, node.id)
        return [(node.id, '!=', False)]
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.left, ast.Name):
        operator = OPERATORS.get(type(node.ops[0]))
        if operator is None:
            raise ConditionError(_lt("This comparison is not supported in a condition."))
        _field(model, node.left.id)
        return [(node.left.id, operator, _value(node.comparators[0], uid))]
    raise ConditionError(_lt(
        "Write the condition as comparisons of fields with values, joined by and, or, not: "
        "state == 'done' and amount_total > 1000"))


def _field(model, name):
    if name not in model._fields:
        raise ConditionError(_lt("The field %(field)s does not exist on %(model)s.", field=name, model=model._name))


def condition_domain(expression, model, uid=False):
    """ The domain matching the records for which the condition holds. """
    return _domain(_parse(expression), model, uid)
