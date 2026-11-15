import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OmInventoryReportSchedule(models.Model):
    """A saved view sent by email at a regular interval, as a PDF or Excel file."""
    _name = 'om.inventory.report.schedule'
    _description = 'Scheduled Inventory Report'
    _order = 'next_date, id'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    view_id = fields.Many2one('om.inventory.report.view', string="Saved View", required=True, ondelete='cascade',
                              help="The report, filters, grouping and columns to send.")
    report_key = fields.Char(related='view_id.report_key')
    file_format = fields.Selection([('pdf', 'PDF'), ('xlsx', 'Excel'), ('csv', 'CSV')], string="Format",
                                   default='xlsx', required=True)
    expand_all = fields.Boolean("All Lines", default=True, help="Unfold every group in the file.")
    interval = fields.Selection([('daily', 'Every day'), ('weekly', 'Every week'), ('monthly', 'Every month')],
                                default='weekly', required=True)
    next_date = fields.Datetime("Next Sending", required=True, default=fields.Datetime.now)
    partner_ids = fields.Many2many('res.partner', string="Recipients", required=True)
    user_id = fields.Many2one('res.users', string="Run As", default=lambda self: self.env.user, required=True,
                              help="The report is made with this user's access rights and companies.")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    last_sent = fields.Datetime(readonly=True)

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
            'report': self.view_id.report_key,
            'format': self.file_format,
            'options': self.view_id.options or {},
            'expanded': [],
            'expand_all': self.expand_all,
        }
        env = self.with_user(self.user_id).with_company(self.company_id).env
        content, filename, mimetype = env['om.inventory.report.export']._om_render_file(params)
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
                _logger.exception("Scheduled inventory report %s failed", schedule.id)
            schedule.next_date = schedule._om_next_date(schedule.next_date)
