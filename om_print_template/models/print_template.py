from odoo import api, fields, models


class PrintTemplate(models.Model):
    """ A PDF any user prints from a record, written in the editor with the fields of the record, e.g. a salary
    certificate of an employee or a balance confirmation of a customer.

    Each template adds an entry to the Print menu of its model. What is printed is kept as an issued print, with a
    reference number and the text frozen as it was printed.
    """
    _name = 'print.template'
    _inherit = ['mail.render.mixin']
    _description = 'Print Template'
    _check_company_auto = True
    _order = 'sequence, name, id'
    # what a template holds is trusted when printed, as for the email templates: only the template editors write
    # dynamic content into it, which the render mixin checks when a template is created or changed
    _unrestricted_rendering = True

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one(
        'ir.model', string='Applies To', required=True, ondelete='cascade', index=True,
        domain=[('transient', '=', False), ('abstract', '=', False)],
        help='The kind of record the template prints, e.g. Employee.')
    model = fields.Char(related='model_id.model', store=True, index=True)
    subject = fields.Char(translate=True, help='The title of the print, e.g. Salary Certificate. Fields of the '
                                               'record may be used, e.g. {{ object.name }}.')
    addressee = fields.Char(translate=True, default=lambda self: self.env._('To Whom It May Concern'),
                            help='Who the print is addressed to. It can be changed when printing.')
    body_html = fields.Html(
        string='Body', render_engine='qweb', render_options={'post_process': True}, prefetch=True,
        translate=True, sanitize='email_outgoing')
    code = fields.Char(string='Reference Prefix', help='Starts the reference of each print, e.g. CERT/.')
    sequence_id = fields.Many2one('ir.sequence', string='Reference Sequence', readonly=True, copy=False,
                                  check_company=True)
    signatory_name = fields.Char(string='Signed By')
    signatory_title = fields.Char(string='Title', translate=True)
    signature = fields.Image(string='Signature or Stamp', max_width=512, max_height=256)
    show_qr = fields.Boolean(
        string='Verification QR',
        help='Print a QR code that opens a public page confirming the print: its reference, date, holder and '
             'whether it is still valid. Banks and embassies use it to check a certificate.')
    print_menu = fields.Boolean(
        string='In the Print Menu', default=True,
        help='Offer the template in the Print menu of the records it applies to.')
    ref_ir_act_window = fields.Many2one('ir.actions.act_window', string='Print Menu Action', readonly=True,
                                        copy=False)
    company_id = fields.Many2one('res.company', help='Leave empty to share the template with all the companies.')
    issue_ids = fields.One2many('print.issue', 'template_id', string='Issued Prints')
    issue_count = fields.Integer(compute='_compute_issue_count', string='Issued')

    @api.depends('model')
    def _compute_render_model(self):
        for template in self:
            template.render_model = template.model

    def _compute_issue_count(self):
        counts = dict(self.env['print.issue']._read_group(
            [('template_id', 'in', self.ids)], ['template_id'], ['__count']))
        for template in self:
            template.issue_count = counts.get(template, 0)

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        for template in templates:
            template.sequence_id = self.env['ir.sequence'].sudo().create(template._sequence_values())
        templates._sync_print_menu()
        return templates

    def write(self, vals):
        result = super().write(vals)
        if {'code', 'name'} & set(vals):
            for template in self.filtered('sequence_id'):
                template.sequence_id.sudo().write(template._sequence_values())
        if {'print_menu', 'name', 'model_id', 'active'} & set(vals):
            self._sync_print_menu()
        return result

    def unlink(self):
        actions = self.sudo().ref_ir_act_window
        sequences = self.sudo().sequence_id
        result = super().unlink()
        actions.unlink()
        sequences.unlink()
        return result

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [dict(vals, name=self.env._('%s (copy)',
                                           template.name)) for template, vals in zip(self, vals_list, strict=True)]

    def _sequence_values(self):
        self.ensure_one()
        return {
            'name': self.env._('Print Template: %s', self.name),
            'code': False,
            'prefix': self.code or '%(year)s/',
            'padding': 4,
            'company_id': False,
        }

    def _sync_print_menu(self):
        """ The entry of each template in the Print menu of its model, opening the print wizard. """
        for template in self.sudo():
            wanted = template.print_menu and template.active
            if not wanted:
                template.ref_ir_act_window.unlink()
                continue
            values = {
                'name': template.name,
                'res_model': 'print.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': repr({'default_template_id': template.id}),
                'binding_model_id': template.model_id.id,
                'binding_type': 'report',
            }
            if template.ref_ir_act_window:
                template.ref_ir_act_window.write(values)
            else:
                template.ref_ir_act_window = self.env['ir.actions.act_window'].create(values)

    def _render_print_values(self, res_ids):
        """ :return: per record id, the subject, the addressee, the body and the language of the print """
        self.ensure_one()
        langs = self._render_lang(res_ids) if self.lang else {}
        rendered = {}
        for field in ('subject', 'addressee', 'body_html'):
            rendered[field] = self._render_field(field, res_ids, compute_lang=True) if self[field] else {}
        return {res_id: {
            'subject': rendered['subject'].get(res_id) or False,
            'addressee': rendered['addressee'].get(res_id) or False,
            'body_html': rendered['body_html'].get(res_id) or False,
            'lang': langs.get(res_id) or False,
        } for res_id in res_ids}

    def action_open_issues(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Issued Prints'),
            'res_model': 'print.issue',
            'view_mode': 'list,form',
            'domain': [('template_id', '=', self.id)],
        }
