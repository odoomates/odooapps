def lock_rows(records):
    """ Grab a write lock on the rows of `records` without waiting, as ``lock_for_update`` of Odoo 19 does.

    :return: whether every row could be locked: a concurrent transaction holding one makes it False
    """
    ids = tuple(records.ids)
    if not ids:
        return True
    records.env.cr.execute('SELECT id FROM "%s" WHERE id IN %%s FOR UPDATE SKIP LOCKED' % records._table, (ids,))
    return len(records.env.cr.fetchall()) == len(ids)
