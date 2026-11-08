# -*- coding: utf-8 -*-
""" What differs between Odoo 10 and Odoo 14 for this module, in one place, so that the same code runs on all of
them (Python 2.7 for Odoo 10, Python 3 from Odoo 11). """
import re

from odoo import api

# Odoo 10 to 12 need @api.multi on the methods of a recordset; Odoo 13 removed it
multi = getattr(api, 'multi', lambda method: method)

# the error codes of PG_CONCURRENCY_EXCEPTIONS_TO_RETRY (Odoo 17): another transaction changed the rows meanwhile.
# psycopg2 is too old in these versions for psycopg2.errors, so the codes are compared.
CONCURRENCY_CODES = ('55P03', '40001', '40P01')  # lock not available, serialization failure, deadlock detected

PLACEHOLDER = re.compile(r'%%|%s')


class SQL(object):
    """ The part of odoo.tools.SQL (Odoo 17 and later) this module uses: a piece of SQL code with %s placeholders,
    each filled with a parameter or with another SQL object, inlined. """
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

    @classmethod
    def identifier(cls, name):
        assert re.match(r'^\w+$', name), name
        return cls('"%s"' % name)


def execute(cr, query, log_exceptions=None):
    """ cr.execute() of a SQL object, which the cursors of these versions do not take """
    cr.execute(query.code, query.params, log_exceptions=log_exceptions)


def savepoint(cr):
    """ A savepoint that does not flush: Odoo 13 and 14 flush by default, Odoo 10 to 12 have nothing to flush """
    try:
        return cr.savepoint(flush=False)
    except TypeError:
        return cr.savepoint()


def flush(env):
    """ Write the pending changes to the database (Odoo 13 and 14; earlier versions write at once) """
    model = env['res.users']
    if hasattr(model, 'flush'):
        model.flush()


def invalidate(env):
    """ Forget every value cached by the ORM and the lookups cached for the deleted XML ids """
    env['res.users'].invalidate_cache()
    env.registry.clear_caches()
