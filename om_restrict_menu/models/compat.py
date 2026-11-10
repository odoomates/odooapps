# -*- coding: utf-8 -*-
""" What differs between Odoo 10 and Odoo 14 for this module, in one place, so that the same code runs on all of
them (Python 2.7 for Odoo 10, Python 3 from Odoo 11). """
from odoo import api
from odoo.http import request

# Odoo 10 to 12 need @api.multi on the methods of a recordset; Odoo 13 removed it
multi = getattr(api, 'multi', lambda method: method)


def as_user(records, user):
    """ ``records`` as ``user``: with_user() from Odoo 13, sudo(user) before """
    if hasattr(records, 'with_user'):
        return records.with_user(user)
    return records.sudo(user)


def origin(records):
    """ The saved records behind those of a form not saved yet: _origin from Odoo 13. Odoo 10 to 12 give the
    saved records, or new ones without a database id. """
    records = getattr(records, '_origin', records)
    return records.browse([record_id for record_id in records._ids if isinstance(record_id, int)])


def current_company(env):
    """ The current company. From Odoo 13 the company switcher keeps the active companies in the cids cookie,
    the current one first, and the menus request carries no context. Before, switching company changes the
    company of the user. """
    if not hasattr(env, 'company'):
        return env.user.company_id
    if request and 'allowed_company_ids' not in env.context:
        current = (request.httprequest.cookies.get('cids') or '').replace(',', '-').split('-')[0]
        if current.isdigit() and int(current) in env.user.company_ids.ids:
            return env['res.company'].browse(int(current))
    return env.company
