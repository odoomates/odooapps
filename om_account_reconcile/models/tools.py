from odoo.tools import SQL


def lock_rows(records):
    """ Grab a write lock on the rows of `records` without waiting, as ``lock_for_update`` of Odoo 19 does.

    :return: whether every row could be locked: a concurrent transaction holding one makes it False
    """
    ids = tuple(records.ids)
    if not ids:
        return True
    locked = records.env.execute_query(SQL(
        "SELECT id FROM %s WHERE id IN %s FOR UPDATE SKIP LOCKED", SQL.identifier(records._table), ids,
    ))
    return len(locked) == len(ids)
