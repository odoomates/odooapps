# The lines reported to the audit log after a transaction (refusals, ended
# sessions). The test cursors cannot show a line written after a rollback, so
# the lines are caught on their way out.
from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def lines_after_transaction(env):
    lines = []
    with patch.object(type(env['om.user.audit.log']), '_om_write_separately', autospec=True,
                      side_effect=lambda log, registry, vals_list: lines.extend(vals_list)):
        yield lines


def has_access(records, operation):
    """ Odoo 17's has_access(): the rights on the model, then the record rules. """
    from odoo.exceptions import AccessError  # noqa: PLC0415
    try:
        records.check_access_rights(operation)
        records.check_access_rule(operation)
    except AccessError:
        return False
    return True
