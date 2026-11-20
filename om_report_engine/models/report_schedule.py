import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class OmReportSchedule(models.Model):
    """A saved view of a report sent by email at a regular interval, as a PDF, Excel or CSV file."""
    _name = 'om.report.schedule'
    _description = 'Scheduled Report'
    _order = 'next_date, id'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    view_id = fields.Many2one('om.report.view', string="Saved View", required=True, ondelete='cascade',
                              help="The report, filters, options and columns to send.")
    report_model = fields.Char(related='view_id.report_model', store=True, index=True)
    report_name = fields.Char(string="Report", compute='_compute_report_name')
    file_format = fields.Selection([('pdf', 'PDF'), ('xlsx', 'Excel'), ('csv', 'CSV')], string="Format",
                                   default='xlsx', required=True)
    expand_all = fields.Boolean("All Lines", default=True, help="Unfold every line in the file.")
    interval = fields.Selection([('daily', 'Every day'), ('weekly', 'Every week'), ('monthly', 'Every month')],
                                default='weekly', required=True)
    next_date = fields.Datetime("Next Sending", required=True, default=fields.Datetime.now)
    partner_ids = fields.Many2many('res.partner', string="Recipients", required=True)
    user_id = fields.Many2one('res.users', string="Run As", default=lambda self: self.env.user, required=True,
                              ondelete='cascade',
                              help="The report is made with this user's access rights and companies.")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True,
                                 ondelete='cascade')
    last_sent = fields.Datetime(readonly=True)

    @api.depends('report_model')
    def _compute_report_name(self):
        for schedule in self:
            report = self.env.get(schedule.report_model) if schedule.report_model else None
            schedule.report_name = report._om_report_title() if report is not None \
                and getattr(report, '_report_name', False) else schedule.report_model

    @api.constrains('user_id')
    def _check_user_id(self):
        # a report runs with the rights of its user: only an administrator sends one as someone else
        if not self.env.user.has_group('base.group_system') and not self.env.su:
            if any(schedule.user_id != self.env.user for schedule in self):
                raise ValidationError(self.env._("A scheduled report runs as the user who creates it."))

    @api.onchange('view_id')
    def _onchange_view_id(self):
        if self.view_id and not self.name:
            self.name = self.view_id.name

    def _om_next_date(self, date):
        step = {'daily': relativedelta(days=1), 'weekly': relativedelta(weeks=1),
                'monthly': relativedelta(months=1)}[self.interval]
        date += step
        while date <= fields.Datetime.now():
            date += step
        return date

    def action_send_now(self):
        for schedule in self:
            schedule._om_send()
        return True

    def _om_send(self):
        self.ensure_one()
        if not self.partner_ids:
            raise UserError(self.env._("Add at least one recipient."))
        params = {
            'model': self.view_id.report_model,
            'format': self.file_format,
            'options': self.view_id.options or {},
            'expanded': [],
            'expand_all': self.expand_all,
        }
        env = self.with_user(self.user_id).with_company(self.company_id).env
        content, filename, mimetype = env['om.report.export']._om_render_file(params)
        attachment = self.env['ir.attachment'].sudo().create({
            'name': filename,
            'raw': content,
            'mimetype': mimetype,
            'res_model': self._name,
            'res_id': self.id,
        })
        body = self.env._("<p>Hello,</p><p>Please find attached the report <b>%(name)s</b>.</p>",
                          name=self.view_id.name)
        mail = self.env['mail.mail'].sudo().create({
            'subject': '%s - %s' % (self.name, filename.rsplit('.', 1)[0]),
            'body_html': body,
            'email_from': self.user_id.email_formatted or self.company_id.email_formatted,
            'recipient_ids': [(6, 0, self.partner_ids.ids)],
            'attachment_ids': [(4, attachment.id)],
            'auto_delete': True,
        })
        mail.send()
        self.last_sent = fields.Datetime.now()

    @api.model
    def _cron_send_due(self):
        for schedule in self.search([('next_date', '<=', fields.Datetime.now())]):
            try:
                with self.env.cr.savepoint():
                    schedule._om_send()
            except Exception:  # noqa: BLE001 - one failing report must not stop the others
                _logger.exception("Scheduled report %s failed", schedule.id)
            schedule.next_date = schedule._om_next_date(schedule.next_date)
