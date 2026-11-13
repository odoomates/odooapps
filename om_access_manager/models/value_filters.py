# Value filters of fields: combined as domain expressions, so that a filter
# reading the record (company_id, parent.partner_id) combines as well as a
# plain literal, both in the views (evaluated by the web client) and in the
# check made when a value is saved.
import ast

OPERATORS = {'&': 2, '|': 2, '!': 1}


def _elements(expression):
    """ The terms of a domain written as a list, as AST nodes, or None when
    the expression is not a list (a name, a call). """
    try:
        node = ast.parse(expression.strip(), mode='eval').body
    except SyntaxError:
        return None
    return list(node.elts) if isinstance(node, ast.List) else None


def _operator(node):
    return node.value if isinstance(node, ast.Constant) and node.value in OPERATORS else None


def _normalized(elements):
    """ ``elements`` as a single prefix term: the implicit ANDs made explicit. """
    result, expected = [], 1
    for node in elements:
        if expected == 0:
            result.insert(0, ast.Constant('&'))
            expected = 1
        result.append(node)
        operator = _operator(node)
        expected += OPERATORS[operator] - 1 if operator else -1
    return result


def _unparse(elements):
    return ast.unparse(ast.List(elts=elements, ctx=ast.Load()))


def and_domains(expressions):
    """ The AND of domain expressions: every one of them must hold. Lists are
    concatenated; anything else is added (``a + b``), which the server and the
    web client both evaluate to the concatenated list. """
    expressions = [e.strip() for e in expressions if e and e.strip()]
    if len(expressions) < 2:
        return expressions[0] if expressions else None
    parsed = [_elements(expression) for expression in expressions]
    if all(elements is not None for elements in parsed):
        return _unparse([node for elements in parsed for node in elements])
    return ' + '.join(f'({expression})' for expression in expressions)


def or_domains(expressions):
    """ The OR of domain expressions: one of them is enough. None when they
    cannot be combined (an expression that is not a list, or an empty one,
    which allows everything): the caller then leaves the values unfiltered. """
    expressions = [e.strip() for e in expressions if e and e.strip()]
    if len(expressions) < 2:
        return expressions[0] if expressions else None
    terms = []
    for expression in expressions:
        elements = _elements(expression)
        if not elements:
            return None
        terms.append(_normalized(elements))
    return _unparse([ast.Constant('|')] * (len(terms) - 1) + [node for term in terms for node in term])


def names_read(expression):
    """ The names an expression reads (fields of the record, uid, parent...). """
    try:
        node = ast.parse(expression.strip(), mode='eval')
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
