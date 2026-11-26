from . import models
from . import wizard


def _om_3way_post_init(env):
    """ Compute the match of the vendor bills already in the database: the columns are created empty at install so
    that the other journal items are not computed one by one. """
    bills = env['account.move'].search([('move_type', '=', 'in_invoice')])
    lines = bills.invoice_line_ids
    env.add_to_compute(env['account.move.line']._fields['om_match_state'], lines)
    env.add_to_compute(env['account.move']._fields['om_release_state'], bills)
    lines.flush_recordset(['om_match_state'])
    bills.flush_recordset(['om_release_state'])
