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
