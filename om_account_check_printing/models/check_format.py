import re

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
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
    ('%d.%m.%Y', 'DD.MM.YYYY'),
    ('%Y/%m/%d', 'YYYY/MM/DD'),
    ('%Y%m%d', 'YYYYMMDD (date boxes)'),
    ('%B %d, %Y', 'Month DD, YYYY'),
]
FIELDS = [
    ('date', 'Date'),
    ('payee', 'Payee'),
    ('amount', 'Amount in Figures'),
    ('amount_in_words', 'Amount in Words'),
    ('amount_in_words_2', 'Amount in Words (Second Language)'),
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
    'routing_number': '011000015',
    'account_number': '1234567890',
}
# the E-13B symbols on the letters where most MICR fonts draw them
MICR_TRANSIT = 'A'
MICR_ON_US = 'C'
MICR_DASH = 'D'


def _lang_get(self):
    return self.env['res.lang'].get_installed()


class AccountCheckFormat(models.Model):
    _name = 'account.check.format'
    _description = 'Cheque Format'
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', help="Leave empty to share the format.")
    country_ids = fields.Many2many(
        'res.country', string='Countries',
        help="Where the cheques of this format are used: a bank journal without a cheque format takes the first "
             "format of the country of its company. Leave empty for a format used anywhere.")
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
    words_lang = fields.Selection(
        _lang_get, string='Language of the Words',
        help="The language of the amount in words, e.g. English on the cheques of the Gulf whatever the language of "
             "the user. Leave empty for the language of the user.")
    words_lang_2 = fields.Selection(
        _lang_get, string='Second Language of the Words',
        help="The language of the Amount in Words (Second Language) field, e.g. Arabic on bilingual cheques.")
    words_cents = fields.Selection(
        [('words', 'In Words'), ('fraction', 'As a Fraction (and 50/100)')],
        string='Cents', required=True, default='words',
        help="How the cents follow the amount in words: in words, or as a fraction as on the cheques of the US.")
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
    print_micr = fields.Boolean(
        string='Print the MICR Line',
        help="Prints the cheque number, the routing number and the account number in magnetic E-13B characters "
             "at the bottom of the cheque, for cheques printed on blank cheque paper with magnetic toner. Leave it "
             "off on the cheques of your bank, where the line is already printed.")
    micr_style = fields.Selection(
        [('us', 'United States (ANSI X9)'), ('ca', 'Canada (CPA-005)')], string='MICR Standard',
        required=True, default='us',
        help="United States: the cheque number, then the routing number, then the account number. Canada: the "
             "cheque number, then the transit and the institution numbers, then the account number.")
    micr_font = fields.Binary(
        string='MICR Font', attachment=True,
        help="A TrueType E-13B font drawing the transit, on-us and dash symbols on the letters A, C and D, as most "
             "MICR fonts do.")
    micr_font_filename = fields.Char(string='MICR Font File Name')
    micr_bottom = fields.Float(
        string='Cheque Bottom Edge (mm)', digits=(16, 1),
        help="Distance from the top of the page to the bottom edge of the cheque: the MICR line is printed at the "
             "standard distance above it. Leave at 0 when the cheque ends with the page.")
    micr_right = fields.Float(
        string='MICR Right Margin (mm)', default=7.9, digits=(16, 1),
        help="Distance from the right edge of the cheque to the end of the MICR line: 5/16 inch in the standards.")
    micr_font_size = fields.Float(string='MICR Font Size (pt)', default=12.0, digits=(16, 1))
    paperformat_id = fields.Many2one('report.paperformat', string='Paper Format', readonly=True, copy=False)
    preview_html = fields.Html(
        string='Preview', compute='_compute_preview_html', sanitize=False,
        help="The test print, with sample values, as it is laid out on the page.")

    @api.depends(
        'paper_size', 'page_width', 'page_height', 'offset_x', 'offset_y', 'font_size', 'date_format',
        'amount_with_currency', 'amount_stars', 'words_uppercase', 'words_suffix', 'words_lang', 'words_lang_2',
        'words_cents', 'words_fill', 'print_stub', 'stub_top', 'stub_2_top', 'print_micr', 'micr_style', 'micr_font',
        'micr_bottom', 'micr_right', 'micr_font_size', 'company_id',
        'line_ids.sequence', 'line_ids.field', 'line_ids.text', 'line_ids.x', 'line_ids.y', 'line_ids.width',
        'line_ids.height', 'line_ids.line_height', 'line_ids.font_size', 'line_ids.bold', 'line_ids.align',
        'line_ids.letter_spacing', 'line_ids.rotation', 'line_ids.border',
    )
    @api.depends_context('lang')
    def _compute_preview_html(self):
        for check_format in self:
            check_format.preview_html = check_format._render_preview()

    def _get_preview_height(self):
        """ :return: the height of the page shown by the preview: down to the last printed thing """
        self.ensure_one()
        width, height = self._get_page_size()
        bottom = max([line.y + max(line.height, line.line_height) for line in self.line_ids] or [0.0])
        if self.print_micr:
            bottom = max(bottom, self.micr_bottom or height)
        if self.print_stub:
            # a stub is a title and a few lines
            bottom = max(bottom, max(self.stub_top, self.stub_2_top) + 60.0)
        return min(height, bottom + max(self.offset_y, 0.0) + 10.0)

    def _render_preview(self):
        """ :return: the test print rendered on a sheet, scaled to the width of the form """
        self.ensure_one()
        try:
            page = self.env['ir.qweb']._render('om_account_check_printing.check_pages', {
                'check_format': self,
                'pages': self._get_sample_pages(),
            })
        except (UserError, ValueError) as error:
            return Markup('<div class="alert alert-warning" role="alert">%s</div>') % (
                _('The preview cannot be shown: %s', error))
        width = self._get_page_size()[0]
        # 1 mm is 96 / 25.4 pixels; the sheet fits in 760 pixels
        scale = min(1.0, 760.0 / (width * 96 / 25.4))
        return Markup(
            '<div class="o_om_check_preview" style="overflow: hidden; height: %.1fmm; max-width: 100%%;">'
            '<div style="zoom: %.3f; width: %.1fmm; height: %.1fmm; overflow: hidden; background: #fff; color: #000; '
            'border: 1px solid #ccc; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);">%s</div></div>'
        ) % (self._get_preview_height() * scale + 1, scale, width, self._get_preview_height(), page)

    @api.constrains('print_micr', 'micr_font')
    def _check_micr_font(self):
        for check_format in self:
            if check_format.print_micr and not check_format.micr_font:
                raise ValidationError(_(
                    'Upload an E-13B font to print the MICR line of the cheque format %s.', check_format.name))

    @api.constrains('paper_size', 'page_width', 'page_height', 'font_size', 'micr_font_size')
    def _check_page(self):
        for check_format in self:
            if check_format.paper_size == 'custom' and (check_format.page_width <= 0 or check_format.page_height <= 0):
                raise ValidationError(_('Set the size of the page of the cheque format %s.', check_format.name))
            if check_format.print_micr and check_format.micr_font_size <= 0:
                raise ValidationError(_('The MICR font size of the cheque format %s must be positive.',
                                        check_format.name))
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

    def _format_words(self, amount, currency, lang=None):
        """ :param lang: the code of the language of the words, else the one of the format or of the user """
        self.ensure_one()
        lang = lang or self.words_lang
        check_format = self.with_context(lang=lang) if lang else self
        currency = currency.with_context(lang=lang) if lang else currency
        if check_format.words_cents == 'fraction':
            amount = currency.round(amount)
            integral = int(amount)
            subunits = 10 ** currency.decimal_places
            cents = int(round((amount - integral) * subunits))
            words = check_format.env._(
                '%(words)s and %(cents)s/%(subunits)s', words=currency.amount_to_text(integral),
                cents=str(cents).zfill(currency.decimal_places), subunits=subunits)
        else:
            words = currency.amount_to_text(amount)
        if check_format.words_suffix:
            words = '%s %s' % (words, check_format.words_suffix)
        if self.words_uppercase:
            words = words.upper()
        return words

    def _format_micr(self, check_number, routing_number, account_number):
        """ :return: the MICR line, whose symbols are drawn by the MICR font """
        self.ensure_one()

        def digits(value):
            return re.sub(r'[^0-9]', '', value or '')

        check_number = digits(check_number)
        routing = digits(routing_number)
        account = digits(account_number)
        if self.micr_style == 'ca':
            # transit (5) and institution (3), also written 0 + institution + transit in electronic payments
            if len(routing) == 9 and routing.startswith('0'):
                routing = routing[4:] + routing[1:4]
            if len(routing) != 8:
                raise UserError(_(
                    'The transit and institution numbers of a Canadian cheque have 8 digits (e.g. 12345-001), '
                    'not %s.', routing_number or '-'))
            transit = '%s%s%s' % (routing[:5], MICR_DASH, routing[5:])
        else:
            if len(routing) != 9:
                raise UserError(_('The routing number of a US cheque has 9 digits, not %s.', routing_number or '-'))
            transit = routing
        if not account:
            raise UserError(_('Set the account number of the bank account to print the MICR line.'))
        return '%(on_us)s%(check)s%(on_us)s %(transit_sym)s%(transit)s%(transit_sym)s %(account)s%(on_us)s' % {
            'on_us': MICR_ON_US, 'transit_sym': MICR_TRANSIT,
            'check': check_number, 'transit': transit, 'account': account,
        }

    def _get_micr_font_face(self):
        """ :return: the CSS declaring the MICR font, embedded so that the PDF engine does not have to fetch it """
        self.ensure_one()
        if not (self.print_micr and self.micr_font):
            return ''
        return Markup(
            "@font-face { font-family: '%s'; src: url(data:font/ttf;base64,%s) format('truetype'); }"
        ) % (self._get_micr_font_family(), Markup(self.micr_font.to_base64()))

    def _get_micr_font_family(self):
        self.ensure_one()
        return 'OmCheckMicr%s' % (self._origin.id or 'New')

    def _get_micr_style(self):
        self.ensure_one()
        width, height = self._get_page_size()
        bottom = self.micr_bottom or height
        # the line sits in the clear band: its baseline 3/16 inch above the bottom edge of the cheque
        font_height = self.micr_font_size * 0.3528
        return '; '.join([
            'position: absolute',
            'left: %.2fmm' % (self.offset_x + 5.0),
            'width: %.2fmm' % (width - 5.0 - self.micr_right),
            'top: %.2fmm' % (bottom - 4.8 - font_height + self.offset_y),
            'line-height: %.2fmm' % font_height,
            'height: %.2fmm' % (font_height + 1),
            'text-align: right',
            'white-space: nowrap',
            "font-family: '%s', monospace" % self._get_micr_font_family(),
            'font-size: %.1fpt' % self.micr_font_size,
        ])

    def _get_field_values(self, partner_name, amount, currency, date, memo, check_number, company, void=False,
                          bank_account=None):
        """ :return: the text printed for each field """
        self.ensure_one()
        micr = ''
        if self.print_micr and not void and bank_account is not None:
            if not bank_account:
                raise UserError(_('Set the bank account of the journal to print the MICR line of the cheques.'))
            micr = self._format_micr(check_number, bank_account.clearing_number, bank_account.account_number)
        return {
            'date': self._format_date(date),
            'payee': partner_name or '',
            'amount': _('VOID') if void else self._format_amount(amount, currency),
            'amount_in_words': _('VOID') if void else self._format_words(amount, currency),
            'amount_in_words_2': (
                '' if void or not self.words_lang_2 else self._format_words(amount, currency, lang=self.words_lang_2)),
            'micr': micr,
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
        if self.print_micr:
            values['micr'] = self._format_micr(
                SAMPLE_VALUES['check_number'],
                '12345001' if self.micr_style == 'ca' else SAMPLE_VALUES['routing_number'],
                SAMPLE_VALUES['account_number'])
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
        if self.field in ('amount_in_words', 'amount_in_words_2') and self.format_id.words_fill and values.get(self.field):
            return '*' * 300
        return ''
