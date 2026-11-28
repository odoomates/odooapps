from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

LOW_CONFIDENCE = 0.7
INSTRUCTIONS = """Read this expense receipt. Give the merchant, the date of the purchase, the total paid with taxes,
the taxes, the currency and a short description of what was bought. Choose the expense category from the allowed
values, or null when none fits."""


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    om_ai_read_state = fields.Selection([
        ('done', 'Read by AI'),
        ('to_check', 'Read by AI, To Check'),
    ], string='AI Reading', copy=False, readonly=True)
    om_ai_read_notes = fields.Text(string='AI Notes', copy=False, readonly=True)

    def _om_ai_receipt(self):
        self.ensure_one()
        attachments = self.message_main_attachment_id | self.attachment_ids.sorted('id', reverse=True)
        Extract = self.env['om.ai.extract']
        return attachments.filtered(lambda a: a.mimetype == 'application/pdf' or Extract._is_image(a.mimetype, a.name))[:1]

    def _om_ai_products(self):
        self.ensure_one()
        Product = self.env['product.product']
        return Product.search([('can_be_expensed', '=', True),
                               *Product._check_company_domain(self.company_id)], limit=100)

    def _om_ai_schema(self, products):
        Extract = self.env['om.ai.extract']
        categories = list(dict.fromkeys(products.mapped('display_name')))
        category = {'type': ['string', 'null'], 'description': 'Expense category'}
        if categories:
            category['enum'] = categories + [None]
        properties = {
            'merchant': {'type': ['string', 'null']},
            'description': {'type': ['string', 'null'], 'description': 'What was bought, in a few words'},
            'date': {'type': ['string', 'null'], 'format': 'date'},
            'currency': {'type': ['string', 'null'], 'description': 'ISO code, e.g. EUR'},
            'total': {'type': ['number', 'null'], 'description': 'Total paid, taxes included'},
            'tax': {'type': ['number', 'null'], 'description': 'Taxes included in the total'},
            'category': category,
        }
        return Extract._schema(properties, required=list(properties))

    def action_om_ai_read_receipt(self):
        for expense in self:
            if expense.state != 'draft':
                raise UserError(self.env._('Only a draft expense can be read.'))
            attachment = expense._om_ai_receipt()
            if not attachment:
                raise UserError(self.env._('Attach the receipt (a photo or a PDF) first.'))
            expense._om_ai_read(attachment)
        if len(self) == 1:
            return True
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'message': self.env._('%s expense(s) read: check them before submitting.', len(self)),
                       'type': 'success', 'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }

    def _om_ai_read(self, attachment):
        self.ensure_one()
        Extract = self.env['om.ai.extract']
        products = self._om_ai_products()
        data, problems, _payload = Extract._extract(attachment.raw, attachment.mimetype, attachment.name,
                                                    self._om_ai_schema(products), instructions=INSTRUCTIONS)
        checks = []
        values = {}
        product = products.filtered(lambda p: p.display_name == data.get('category'))[:1]
        if product:
            values['product_id'] = product.id
        elif not self.product_id:
            checks.append(self.env._('No expense category fits: choose one.'))
        if data.get('date'):
            values['date'] = data['date']
            if fields.Date.to_date(data['date']) > fields.Date.context_today(self):
                checks.append(self.env._('The date read is in the future.'))
        else:
            checks.append(self.env._('No date was read.'))
        name = ' - '.join(filter(None, [data.get('merchant'), data.get('description')]))
        if name:
            values['name'] = name[:200]
        if data.get('merchant'):
            vendor = self.env['res.partner'].search([('name', '=ilike', data['merchant']),
                                                     *self.env['res.partner']._check_company_domain(self.company_id)],
                                                    limit=2)
            if len(vendor) == 1:
                values['vendor_id'] = vendor.id
        currency = self.env['res.currency'].with_context(active_test=False).search(
            [('name', '=', (data.get('currency') or '').upper())], limit=1) if data.get('currency') else None
        if currency and not currency.active:
            checks.append(self.env._('The receipt is in %s, a currency that is not active.', currency.name))
            currency = None
        if values:
            self.write(values)
        if not self.product_has_cost:
            amounts = {}
            if currency:
                amounts['currency_id'] = currency.id
            if data.get('total') is not None:
                amounts['total_amount_currency'] = data['total']
            else:
                checks.append(self.env._('No total was read.'))
            if amounts:
                self.write(amounts)
            if data.get('tax') is not None and self.tax_ids and float_compare(
                    self.tax_amount_currency, data['tax'], precision_rounding=self.currency_id.rounding):
                checks.append(self.env._('The taxes printed (%(read)s) differ from the taxes computed (%(computed)s).',
                                         read=data['tax'], computed=self.tax_amount_currency))
        if data.get('confidence') is not None and data['confidence'] < LOW_CONFIDENCE:
            checks.append(self.env._('The AI is not sure of this reading.'))
        notes = list(data['flags']) + problems + checks
        self.write({
            'om_ai_read_state': 'to_check' if notes else 'done',
            'om_ai_read_notes': '\n'.join(notes) or False,
        })
        self.message_post(body=Extract._summary_html(data, problems, checks))

    @api.model
    def _om_ai_read_new(self, expenses):
        """Read the receipts of expenses just created from uploaded files."""
        for expense in expenses:
            attachment = expense._om_ai_receipt()
            if attachment and expense.state == 'draft':
                try:
                    with self.env.cr.savepoint():
                        expense._om_ai_read(attachment)
                except UserError as error:
                    expense.message_post(body=self.env._('The receipt could not be read by the AI: %s',
                                                         error.args[0] if error.args else error))

    @api.model
    def create_expense_from_attachments(self, attachment_ids=None, view_type='list'):
        expense_ids = super().create_expense_from_attachments(attachment_ids=attachment_ids, view_type=view_type)
        if self.env['ir.config_parameter'].sudo().get_bool('om_ai_extract_expense.read_on_upload'):
            self._om_ai_read_new(self.browse(expense_ids))
        return expense_ids
