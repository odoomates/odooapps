""" Markers of the operations the loans run themselves, set in the context.

The value is an object, not a boolean: a client (the web client, RPC) can only send JSON values in its context,
so it cannot pass itself off as the loan and skip the protections of the schedule (Odoo marks its own lock date
bypass the same way).
"""

LOAN_INTERNAL = object()

# the entries of the schedule are reversed or cancelled by the loan
LOAN_REVERSE = 'loan_reverse'
# the loan writes its schedule lines, paid ones included
SCHEDULE_UPDATE = 'loan_schedule_update'
# the loan writes its own terms, without computing the schedule again
NO_REGENERATE = 'loan_no_regenerate'
# the loan writes its operations and links its entries
LOAN_WRITE = 'loan_write'


def internal(env, key):
    """ Whether the loan itself runs the operation `key` (a marker set by `internal_context`). """
    return env.context.get(key) is LOAN_INTERNAL


def internal_context(*keys):
    """ The context values marking the operations `keys` as run by the loan. """
    return dict.fromkeys(keys, LOAN_INTERNAL)
