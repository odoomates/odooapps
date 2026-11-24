""" Arch helpers of the Studio editor.

The editor shows a real view rendered from the draft arch. Every element of that
arch carries a node id as a CSS class (``o_pen_n<id>``); the web client copies the
classes of the arch onto what it renders, so a click on the screen can be mapped
back to the node it came from. Changes are then sent as operations on node ids and
turned here into inheritance specs whose locators are as stable as possible: a
named node is found by its name, and only an anonymous one by its position.
"""
import ast
import re

from lxml import etree

NODE_CLASS = 'o_pen_n'
HIDDEN_CLASS = 'o_pen_hidden'
NODE_RE = re.compile(r'\b%s(\d+)\b' % NODE_CLASS)

# the attribute that names a node of each tag, when it has one
ID_ATTRS = {
    'field': 'name',
    'button': 'name',
    'page': 'name',
    'group': 'name',
    'filter': 'name',
    'notebook': 'name',
    'separator': 'name',
    'div': 'name',
    'widget': 'name',
    'label': 'for',
    'searchpanel': None,
}
# tags a view has at most once, found by their tag alone
SINGLE_TAGS = ('header', 'sheet', 'chatter', 'templates', 'searchpanel', 'footer')
# tags that are never rendered as such, so a class on them would go nowhere
UNRENDERED_TAGS = ('t', 'templates', 'attribute', 'xpath', 'data')
CONDITION_ATTRS = ('invisible', 'readonly', 'required', 'column_invisible')


def quote(value):
    """ An XPath string literal for `value`, whatever quotes it holds. """
    if "'" not in value:
        return "'%s'" % value
    if '"' not in value:
        return '"%s"' % value
    parts = value.split("'")
    return "concat(%s)" % ", \"'\", ".join("'%s'" % part for part in parts)


def is_element(node):
    return isinstance(node.tag, str)


def elements(root):
    """ The elements of an arch, in document order, comments left out. """
    return [node for node in root.iter() if is_element(node)]


def locator(node, root):
    """ An xpath finding `node` in `root`, by name when it can.

    A positional step is only used below the nearest ancestor that can be found by
    name, so a module adding a field somewhere else in the view does not move the
    customization along with it.
    """
    if node is root:
        return '/%s' % root.tag
    tag = node.tag
    attr = ID_ATTRS.get(tag)
    if attr and node.get(attr):
        expr = '//%s[@%s=%s]' % (tag, attr, quote(node.get(attr)))
        if len(root.xpath(expr)) == 1:
            return expr
    if tag in SINGLE_TAGS and len(root.xpath('//%s' % tag)) == 1:
        return '//%s' % tag
    parent = node.getparent()
    same = [child for child in parent if is_element(child) and child.tag == tag]
    return '%s/%s[%d]' % (locator(parent, root), tag, same.index(node) + 1)


def is_set(value):
    """ Whether a condition attribute is on: anything but empty, 0 or False. """
    return bool(value) and value.strip() not in ('0', 'False', 'false')


def annotate(root, show_hidden=False):
    """ Number the nodes of `root` in place and describe them.

    :param show_hidden: drop the invisible conditions, so hidden nodes are on screen
        to be edited, and mark them so they can be told apart
    :return: {id: description} of every node that carries an id
    """
    nodes = {}
    for index, node in enumerate(elements(root)):
        if node.tag in UNRENDERED_TAGS:
            continue
        info = {
            'id': index,
            'tag': node.tag,
            'attrs': dict(node.attrib),
            'parent': None,
            'text': (node.text or '').strip()[:80],
        }
        classes = [NODE_CLASS + str(index)]
        if show_hidden:
            hidden = False
            for name in ('invisible', 'column_invisible'):
                if is_set(node.get(name)) and node.tag != 'attribute':
                    hidden = True
                    del node.attrib[name]
            if hidden:
                info['hidden'] = True
                classes.append(HIDDEN_CLASS)
        if node.get('class'):
            classes.insert(0, node.get('class'))
        node.set('class', ' '.join(classes))
        nodes[index] = info
    _link_parents(root, nodes)
    return nodes


def _link_parents(root, nodes):
    # one list kept alive for the whole walk: lxml hands back the same proxy objects
    # only while they are referenced, so their ids are stable only then
    items = elements(root)
    position = {id(node): index for index, node in enumerate(items)}
    for index, node in enumerate(items):
        if index not in nodes:
            continue
        parent = node.getparent()
        while parent is not None and position.get(id(parent)) not in nodes:
            parent = parent.getparent()
        nodes[index]['parent'] = position.get(id(parent)) if parent is not None else None
        # the x2many fields the node sits in, outermost first: they tell which model
        # its fields belong to, so the panel offers the right ones
        nodes[index]['owners'] = [
            owner.get('name') for owner in reversed(list(node.iterancestors('field')))
        ]


def node_by_id(root, node_id):
    """ The element numbered `node_id` by `annotate`, on an arch built the same way. """
    items = elements(root)
    if not isinstance(node_id, int) or not 0 <= node_id < len(items):
        return None
    return items[node_id]


def spec(expr, position, *children, **attributes):
    node = etree.Element('xpath', expr=expr, position=position)
    for name, value in attributes.items():
        node.set(name, value)
    node.extend(children)
    return node


def attributes_spec(expr, values):
    """ Set (or, with None, remove) attributes of the node found by `expr`. """
    node = spec(expr, 'attributes')
    for name, value in values.items():
        element = etree.SubElement(node, 'attribute', name=name)
        if value is not None and value is not False:
            element.text = str(value)
    return node


def check_expression(value):
    """ Raise ValueError when `value` is not a python expression the client can read. """
    ast.parse(value.strip(), mode='eval')


def check_literal(value):
    """ Raise ValueError when `value` is neither a literal nor an expression. """
    value = value.strip()
    try:
        ast.literal_eval(value)
    except (ValueError, SyntaxError):
        # domains and contexts may hold names of the record, such as uid or parent
        ast.parse(value, mode='eval')


def to_string(node):
    return etree.tostring(node, encoding='unicode')


def from_string(text):
    return etree.fromstring(text)
