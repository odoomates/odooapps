import uuid

from werkzeug.urls import url_encode

from odoo import api, fields, models
from odoo.exceptions import UserError

# what an issued print keeps as it was printed
FROZEN_FIELDS = {'template_id', 'res_model', 'res_id', 'date', 'addressee', 'subject', 'body_html', 'lang'}


class PrintIssue(models.Model):
    """ A print of a template for a record: drafted, then issued with a reference and its PDF.

    The text is rendered when the print is drafted and may be adjusted until it is issued; from then on it stays as
    printed, so that printing it again gives the same PDF, whatever changed on the record since.
    """
    _name = 'print.issue'
    _inherit = ['mail.thread']
    _description = 'Issued Print'
    _check_company_auto = True
    _order = 'date desc, id desc'
    _mail_post_access = 'read'

    name = fields.Char(string='Reference', required=True, readonly=True, copy=False,
                       default=lambda self: self.env._('Draft'))
    template_id = fields.Many2one('print.template', required=True, ondelete='restrict',
                                 index=True, tracking=True, check_company=True)
    res_model = fields.Char(string='Model', required=True, index=True)
    res_id = fields.Many2oneReference(string='Record ID', model_field='res_model', required=True, index=True)
    res_name = fields.Char(string='Printed For', compute='_compute_res_name')
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    addressee = fields.Char()
    subject = fields.Char()
    body_html = fields.Html(string='Body', sanitize='email_outgoing')
    lang = fields.Char(string='Language')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('cancelled', 'Cancelled'),
    ], required=True, default='draft', copy=False, index=True, tracking=True)
    issued_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    date_issued = fields.Datetime(string='Issued On', readonly=True, copy=False)
    attachment_id = fields.Many2one('ir.attachment', string='PDF', readonly=True, copy=False)
    cancel_reason = fields.Text(readonly=True, copy=False)
    can_cancel = fields.Boolean(compute='_compute_can_cancel',
                                help='Whether the current user may cancel the print, as the server checks it.')
    show_qr = fields.Boolean(related='template_id.show_qr')
    access_token = fields.Char(copy=False, readonly=True, index='btree_not_null', groups='base.group_user')
    signatory_name = fields.Char(related='template_id.signatory_name')
    signatory_title = fields.Char(related='template_id.signatory_title')
    signature = fields.Image(related='template_id.signature')
    company_id = fields.Many2one('res.company', required=True, index=True,
                                 default=lambda self: self.env.company)

    @api.depends('res_model', 'res_id')
    def _compute_res_name(self):
        for issue in self:
            record = issue._get_record()
            issue.res_name = record.sudo().display_name if record else False

    def _get_record(self):
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env or not self.res_id:
            return None
        return self.env[self.res_model].browse(self.res_id).exists()

    def _get_verify_url(self):
        self.ensure_one()
        token = self.sudo().access_token
        return token and '%s/print/verify/%s' % (self.get_base_url(), token)

    def _get_qr_src(self):
        """ :return: the QR code image of the verification page, for the PDF """
        self.ensure_one()
        url = self._get_verify_url()
        return url and '/report/barcode/?%s' % url_encode({
            'barcode_type': 'QR', 'value': url, 'width': 140, 'height': 140, 'quiet': 0})

    # ------------------------------------------------------------------
    # Drafting
    # ------------------------------------------------------------------

    @api.model
    def _create_from_template(self, template, res_ids, values=None):
        """ :return: a draft print of the template for each record, its text rendered from the record """
        rendered = template._render_print_values(res_ids)
        record_model = self.env[template.model]
        vals_list = []
        for res_id in res_ids:
            record = record_model.browse(res_id)
            company = record.company_id if 'company_id' in record._fields and record.company_id \
                else self.env.company
            vals_list.append({
                'template_id': template.id,
                'res_model': template.model,
                'res_id': res_id,
                'company_id': company.id,
                **rendered[res_id],
                **(values or {}),
            })
        return self.create(vals_list)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('access_token', uuid.uuid4().hex)
        return super().create(vals_list)

    def write(self, vals):
        if FROZEN_FIELDS & set(vals) and any(issue.state != 'draft' for issue in self):
            raise UserError(self.env._('An issued print stays as it was printed: cancel it and print it again '
                                       'instead.'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_issued(self):
        if any(issue.state != 'draft' for issue in self):
            raise UserError(self.env._('Only a draft print can be deleted: cancel an issued one instead.'))

    # ------------------------------------------------------------------
    # Issuing
    # ------------------------------------------------------------------

    def action_issue(self):
        """ Number the drafts, print their PDF and keep it. """
        for issue in self:
            if issue.state != 'draft':
                raise UserError(self.env._('%s is already issued.', issue.name))
            sequence = issue.template_id.sudo().sequence_id
            issue.write({
                'name': sequence.next_by_id(issue.date) if sequence else issue.name,
                'state': 'issued',
                'issued_by_id': self.env.uid,
                'date_issued': fields.Datetime.now(),
            })
            issue._attach_pdf()
            issue._on_issued()
        return True

    def _attach_pdf(self):
        self.ensure_one()
        pdf, _type = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'om_print_template.action_report_print_issue', res_ids=self.ids)
        self.attachment_id = self.env['ir.attachment'].sudo().create({
            'name': '%s.pdf' % self.name.replace('/', '_'),
            'raw': pdf,
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': self.id,
        })

    def _on_issued(self):
        """ Hook: the print is issued and its PDF attached. """

    @api.depends_context('uid')
    def _compute_can_cancel(self):
        for issue in self:
            try:
                issue._check_can_cancel()
            except UserError:
                issue.can_cancel = False
            else:
                issue.can_cancel = True

    def _check_can_cancel(self):
        """ Raise unless the current user may cancel the prints: the print administrators. """
        if not self.env.su and not self.env.user.has_group('om_print_template.group_print_manager'):
            raise UserError(self.env._('Only the print administrators cancel an issued print.'))

    def action_cancel(self, reason=False):
        self._check_can_cancel()
        for issue in self:
            if issue.state == 'cancelled':
                continue
            issue.write({'state': 'cancelled', 'cancel_reason': reason or False})
            issue._on_cancelled()
        return True

    def _on_cancelled(self):
        """ Hook: the print is cancelled, its verification page says so. """

    def action_download(self):
        """ The PDF as it was issued, or a preview of the draft. """
        self.ensure_one()
        if self.state != 'draft' and self.attachment_id:
            return {
                'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % self.attachment_id.id,
                'target': 'download',
            }
        return self.env.ref('om_print_template.action_report_print_issue').report_action(self)

    def action_open_record(self):
        self.ensure_one()
        if not self._get_record():
            raise UserError(self.env._('The record of %s no longer exists.', self.name))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
