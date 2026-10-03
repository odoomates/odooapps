import re

PLACEHOLDER = re.compile(r'%%|%s')


class SQL:
    """ The part of odoo.tools.SQL (Odoo 17 and later) this module uses, for Odoo 16: a piece of SQL code with
    %s placeholders, each filled with a parameter or with another SQL object, inlined.

        cr.execute(*SQL("SELECT id FROM res_partner WHERE id IN %s", ids).args)
    """
    __slots__ = ('code', 'params')

    def __init__(self, code='', *args):
        if not args:
            self.code, self.params = code, []
            return
        args = iter(args)
        params = []

        def fill(match):
            if match.group(0) == '%%':
                return '%%'
            arg = next(args)
            if isinstance(arg, SQL):
                params.extend(arg.params)
                return arg.code
            params.append(arg)
            return '%s'

        self.code = PLACEHOLDER.sub(fill, code)
        self.params = params

    @property
    def args(self):
        """ the arguments of cursor.execute() """
        return self.code, self.params

    def join(self, items):
        items = list(items)
        return SQL(self.code.join(['%s'] * len(items)) if items else '', *items) if items else SQL()

    @classmethod
    def identifier(cls, name):
        assert re.match(r'^\w+$', name), name
        return cls('"%s"' % name)


def execute(cr, query):
    """ cr.execute() of a SQL object, which the cursor of Odoo 16 does not take """
    cr.execute(query.code, query.params)
