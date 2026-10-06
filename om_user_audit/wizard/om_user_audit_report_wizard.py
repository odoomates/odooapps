# The activity of users over a period, as a PDF for an audit.
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.om_user_audit_log import EVENTS

LINES_LIMIT = 5000


class OmUserAuditReportWizard(models.TransientModel):
    _name = 'om.user.audit.report.wizard'
    _description = 'User Activity Report'

    user_ids = fields.Many2many('res.users', string='Users', help="Left empty, every user.")
    date_from = fields.Date(string='From', required=True,
                            default=lambda self: fields.Date.context_today(self) - timedelta(days=30))
    date_to = fields.Date(string='To', required=True, default=fields.Date.context_today)
    events = fields.Selection([('all', 'Everything'), ('changes', 'Changes, exports, imports and prints'),
                               ('sign_in', 'Sign-ins and sessions')],
                              string='Events', default='changes', required=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'res.users' and self.env.context.get('active_ids'):
            values['user_ids'] = [(6, 0, self.env.context['active_ids'])]
        return values

    def _domain(self):
        self.ensure_one()
        domain = [('date', '>=', datetime.combine(self.date_from, time.min)),
                  ('date', '<', datetime.combine(self.date_to + timedelta(days=1), time.min))]
        if self.user_ids:
            domain.append(('user_id', 'in', self.user_ids.ids))
        if self.events == 'changes':
            domain.append(('event', 'in', ('create', 'write', 'unlink', 'export', 'import', 'print', 'refused')))
        elif self.events == 'sign_in':
            domain.append(('event', 'in', ('login', 'login_failed', 'logout', 'session_end')))
        return domain

    def action_print(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_("The period ends before it starts."))
        lines = self.env['om.user.audit.log'].search(self._domain(), limit=LINES_LIMIT + 1, order='user_id, id')
        if not lines:
            raise UserError(_("Nothing was logged for these users over this period."))
        return self.env.ref('om_user_audit.action_report_user_activity').report_action(
            self, data={'wizard_id': self.id})

    @api.model
    def _report_values(self, wizard_id):
        wizard = self.browse(wizard_id).exists()
        lines = self.env['om.user.audit.log'].search(wizard._domain(), limit=LINES_LIMIT + 1, order='user_id, id')
        labels = dict(EVENTS)
        groups = {}
        for line in lines[:LINES_LIMIT]:
            groups.setdefault(line.user_id, []).append(line)
        return {
            'wizard': wizard,
            'groups': list(groups.items()),
            'labels': labels,
            'truncated': len(lines) > LINES_LIMIT,
            'limit': LINES_LIMIT,
        }


class ReportUserActivity(models.AbstractModel):
    _name = 'report.om_user_audit.report_user_activity'
    _description = 'User Activity Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard_id = (data or {}).get('wizard_id') or (docids[0] if docids else False)
        return self.env['om.user.audit.report.wizard']._report_values(wizard_id)
