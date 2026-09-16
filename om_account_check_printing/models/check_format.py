from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.misc import format_date, formatLang

PAPER_SIZES = {
    'a4': (210.0, 297.0),
    'letter': (215.9, 279.4),
}
DATE_FORMATS = [
    ('locale', 'Language format'),
    ('%d/%m/%Y', 'DD/MM/YYYY'),
    ('%m/%d/%Y', 'MM/DD/YYYY'),
    ('%Y-%m-%d', 'YYYY-MM-DD'),
    ('%d-%m-%Y', 'DD-MM-YYYY'),
    ('%d%m%Y', 'DDMMYYYY (date boxes)'),
    ('%d %b %Y', 'DD Mon YYYY'),
]
FIELDS = [
    ('date', 'Date'),
    ('payee', 'Payee'),
    ('amount', 'Amount in Figures'),
    ('amount_in_words', 'Amount in Words'),
    ('memo', 'Memo'),
    ('check_number', 'Cheque Number'),
    ('company', 'Company Name'),
    ('text', 'Fixed Text'),
]
# what the test print shows
SAMPLE_VALUES = {
    'partner_name': 'Sample Supplier Ltd',
    'amount': 12345.67,
    'memo': 'INV/2026/0042',
    'check_number': '000123',
}


class AccountCheckFormat(models.Model):
    _name = 'account.check.format'
    _description = 'Cheque Format'
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', help="Leave empty to share the format.")
    paper_size = fields.Selection(
        [('a4', 'A4'), ('letter', 'US Letter'), ('custom', 'Custom (cheque leaf)')],
        string='Paper', required=True, default='a4',
    )
    page_width = fields.Float(string='Page Width (mm)', default=210.0, digits=(16, 1))
    page_height = fields.Float(string='Page Height (mm)', default=297.0, digits=(16, 1))
    offset_x = fields.Float(
        string='Move Right (mm)', digits=(16, 1),
        help="Moves everything to the right (negative: to the left) to adjust to the printer.")
    offset_y = fields.Float(
        string='Move Down (mm)', digits=(16, 1),
        help="Moves everything down (negative: up) to adjust to the printer.")
    font_size = fields.Float(string='Font Size (pt)', default=11.0, digits=(16, 1))
    date_format = fields.Selection(DATE_FORMATS, string='Date Format', required=True, default='%d/%m/%Y')
    amount_with_currency = fields.Boolean(string='Currency Symbol on the Amount')
    amount_stars = fields.Boolean(
        string='Stars around the Amount', default=True, help="**12,345.67** so that nothing can be added.")
    words_uppercase = fields.Boolean(string='Amount in Words in Capitals', default=True)
    words_suffix = fields.Char(string='Words Suffix', translate=True, help="e.g. Only")
    words_fill = fields.Boolean(
        string='Fill the Words Line with Stars', default=True,
        help="Fills the rest of the amount in words box with stars.")
    line_ids = fields.One2many('account.check.format.line', 'format_id', string='Printed Fields', copy=True)
    print_stub = fields.Boolean(
        string='Print Payment Stubs',
        help="Prints the bills paid by the cheque on the rest of the page, e.g. for cheques on top of an A4 page.")
    stub_top = fields.Float(string='First Stub Top (mm)', default=100.0, digits=(16, 1))
    stub_2_top = fields.Float(
        string='Second Stub Top (mm)', digits=(16, 1), help="Leave at 0 to print a single stub.")
    paperformat_id = fields.Many2one('report.paperformat', string='Paper Format', readonly=True, copy=False)

    @api.constrains('paper_size', 'page_width', 'page_height', 'font_size')
    def _check_page(self):
        for check_format in self:
            if check_format.paper_size == 'custom' and (check_format.page_width <= 0 or check_format.page_height <= 0):
                raise ValidationError(_('Set the size of the page of the cheque format %s.', check_format.name))
            if check_format.font_size <= 0:
                raise ValidationError(_('The font size of the cheque format %s must be positive.', check_format.name))

    @api.onchange('paper_size')
    def _onchange_paper_size(self):
        if self.paper_size in PAPER_SIZES:
            self.page_width, self.page_height = PAPER_SIZES[self.paper_size]

    def _get_page_size(self):
        self.ensure_one()
        return PAPER_SIZES.get(self.paper_size) or (self.page_width, self.page_height)

    @api.model_create_multi
    def create(self, vals_list):
        formats = super().create(vals_list)
        formats._sync_paperformat()
        return formats

    def write(self, vals):
        res = super().write(vals)
        if {'name', 'paper_size', 'page_width', 'page_height'} & set(vals):
            self._sync_paperformat()
        return res

    def _sync_paperformat(self):
        """ Keep the paper format of the cheques, without margins so that the positions are measured from the
        edges of the page. The reports are printed in read-only transactions: it is written with the format. """
        for check_format in self:
            width, height = check_format._get_page_size()
            values = {
                'name': _('Cheque: %s', check_format.name),
                'format': {'a4': 'A4', 'letter': 'Letter'}.get(check_format.paper_size, 'custom'),
                'page_width': width if check_format.paper_size == 'custom' else 0,
                'page_height': height if check_format.paper_size == 'custom' else 0,
                'orientation': 'Portrait',
                'margin_top': 0.0,
                'margin_bottom': 0.0,
                'margin_left': 0.0,
                'margin_right': 0.0,
                'header_line': False,
                'header_spacing': 0,
                'dpi': 96,
                'disable_shrinking': True,
            }
            if check_format.paperformat_id:
                check_format.paperformat_id.sudo().write(values)
            else:
                super(AccountCheckFormat, check_format).write({
                    'paperformat_id': self.env['report.paperformat'].sudo().create(values).id,
                })

    def unlink(self):
        paperformats = self.paperformat_id.sudo()
        res = super().unlink()
        paperformats.unlink()
        return res

    # -------------------------------------------------------------------------
    # Printed values
    # -------------------------------------------------------------------------

    def _format_date(self, date):
        self.ensure_one()
        if not date:
            return ''
        if self.date_format == 'locale':
            return format_date(self.env, date)
        return date.strftime(self.date_format)

    def _format_amount(self, amount, currency):
        self.ensure_one()
        if self.amount_with_currency:
            text = formatLang(self.env, amount, currency_obj=currency)
        else:
            text = formatLang(self.env, amount, digits=currency.decimal_places)
        return '**%s**' % text if self.amount_stars else text

    def _format_words(self, amount, currency):
        self.ensure_one()
        words = currency.amount_to_text(amount)
        if self.words_suffix:
            words = '%s %s' % (words, self.words_suffix)
        if self.words_uppercase:
            words = words.upper()
        return words

    def _get_field_values(self, partner_name, amount, currency, date, memo, check_number, company, void=False):
        """ :return: the text printed for each field """
        self.ensure_one()
        return {
            'date': self._format_date(date),
            'payee': partner_name or '',
            'amount': _('VOID') if void else self._format_amount(amount, currency),
            'amount_in_words': _('VOID') if void else self._format_words(amount, currency),
            'memo': memo or '',
            'check_number': check_number or '',
            'company': company.name or '',
        }

    def _get_sample_pages(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        stub_lines = [{
            'due_date': format_date(self.env, fields.Date.context_today(self)),
            'number': 'BILL/2026/%04d' % index,
            'amount_total': formatLang(self.env, 4115.22 + index, currency_obj=company.currency_id),
            'amount_residual': '-',
            'amount_paid': formatLang(self.env, 4115.22 + index, currency_obj=company.currency_id),
            'currency': company.currency_id,
        } for index in range(1, 4)]
        values = self._get_field_values(
            SAMPLE_VALUES['partner_name'], SAMPLE_VALUES['amount'], company.currency_id,
            fields.Date.context_today(self), SAMPLE_VALUES['memo'], SAMPLE_VALUES['check_number'], company)
        return [{'values': values, 'stub_lines': stub_lines, 'partner_name': SAMPLE_VALUES['partner_name']}]

    def action_print_test(self):
        self.ensure_one()
        return self.env.ref('om_account_check_printing.action_report_check_test').with_context(
            om_check_format_id=self.id).report_action(self, config=False)


class AccountCheckFormatLine(models.Model):
    _name = 'account.check.format.line'
    _description = 'Cheque Format Field'
    _order = 'sequence, id'

    format_id = fields.Many2one('account.check.format', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    field = fields.Selection(FIELDS, required=True, default='date')
    text = fields.Char(translate=True, help="The text printed by a Fixed Text field, e.g. A/C PAYEE ONLY.")
    x = fields.Float(string='Left (mm)', digits=(16, 1), help="Distance from the left edge of the page.")
    y = fields.Float(string='Top (mm)', digits=(16, 1), help="Distance from the top edge of the page.")
    width = fields.Float(string='Width (mm)', default=80.0, digits=(16, 1))
    height = fields.Float(
        string='Height (mm)', digits=(16, 1),
        help="Leave at 0 for a single line. A taller box wraps the text, e.g. the amount in words on two lines.")
    line_height = fields.Float(string='Line Spacing (mm)', default=8.0, digits=(16, 1))
    font_size = fields.Float(string='Font Size (pt)', digits=(16, 1), help="Leave at 0 for the size of the format.")
    bold = fields.Boolean()
    align = fields.Selection(
        [('left', 'Left'), ('center', 'Center'), ('right', 'Right')], default='left', required=True)
    letter_spacing = fields.Float(
        string='Letter Spacing (mm)', digits=(16, 2),
        help="Spreads the characters, e.g. the digits of a date in boxes.")
    rotation = fields.Integer(string='Rotation (°)', help="e.g. -30 for an A/C Payee crossing.")
    border = fields.Selection(
        [('none', 'None'), ('box', 'Box'), ('crossing', 'Two Lines (crossing)')], default='none', required=True)

    @api.constrains('width', 'height', 'line_height')
    def _check_size(self):
        for line in self:
            if line.width <= 0 or line.height < 0 or line.line_height <= 0:
                raise ValidationError(_('The width and the line spacing of a printed field must be positive.'))

    def _get_style(self):
        self.ensure_one()
        check_format = self.format_id
        styles = [
            'position: absolute',
            'left: %.2fmm' % (self.x + check_format.offset_x),
            'top: %.2fmm' % (self.y + check_format.offset_y),
            'width: %.2fmm' % self.width,
            'font-size: %.1fpt' % (self.font_size or check_format.font_size),
            'line-height: %.2fmm' % self.line_height,
            'text-align: %s' % self.align,
            'font-weight: %s' % ('bold' if self.bold else 'normal'),
        ]
        if self.height:
            styles += ['height: %.2fmm' % self.height, 'overflow: hidden']
        else:
            styles += ['white-space: nowrap', 'overflow: hidden']
        if self.letter_spacing:
            styles.append('letter-spacing: %.2fmm' % self.letter_spacing)
        if self.rotation:
            # the -webkit- prefixes for wkhtmltopdf
            styles += ['-webkit-transform: rotate(%ddeg)' % self.rotation, 'transform: rotate(%ddeg)' % self.rotation,
                       '-webkit-transform-origin: left top', 'transform-origin: left top']
        if self.border == 'box':
            styles.append('border: 1px solid #000')
        elif self.border == 'crossing':
            styles += ['border-top: 1px solid #000', 'border-bottom: 1px solid #000']
        return '; '.join(styles)

    def _get_text(self, values):
        self.ensure_one()
        if self.field == 'text':
            return self.text or ''
        return values.get(self.field, '')

    def _get_fill(self, values):
        """ :return: the stars filling the rest of the amount in words box, which hides what does not fit """
        self.ensure_one()
        if self.field == 'amount_in_words' and self.format_id.words_fill and values.get(self.field):
            return '*' * 300
        return ''
