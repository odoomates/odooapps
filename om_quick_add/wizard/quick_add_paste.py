from odoo import api, fields, models
from odoo.fields import Command

class OmQuickAddPaste(models.TransientModel):
    _name = 'om.quick.add.paste'
    _inherit = 'om.quick.add.wizard'
    _description = 'Paste Lines'

    text = fields.Text(string="Lines")
    step = fields.Selection([('paste', "Paste"), ('check', "Check")], default='paste', required=True)
    line_ids = fields.One2many('om.quick.add.paste.line', 'wizard_id')
    found_count = fields.Integer(compute='_compute_counts')
    open_count = fields.Integer(compute='_compute_counts')

    @api.depends('line_ids.state')
    def _compute_counts(self):
        for wizard in self:
            wizard.found_count = len(wizard.line_ids.filtered(lambda l: l.state == 'found'))
            wizard.open_count = len(wizard.line_ids) - wizard.found_count

    def _om_qa_read_row(self, document, row):
        """The values of a pasted line for a row; None for an empty row."""
        reading = document._om_qa_read_row(row)
        if not reading:
            return None
        products = reading['products']
        return {
            'row': row.strip(),
            'product_id': products.id if len(products) == 1 else False,
            'candidate_ids': [Command.set(products.ids if len(products) > 1 else [])],
            'quantity': reading['quantity'],
            'price_unit': reading['price_unit'] or 0.0,
            'has_price': reading['price_unit'] is not None,
        }

    def action_check(self):
        self.ensure_one()
        document = self._om_qa_document()
        lines = []
        for sequence, row in enumerate((self.text or '').splitlines()):
            if not row.strip():
                continue
            values = self._om_qa_read_row(document, row)
            if values:
                lines.append(Command.create({**values, 'sequence': sequence}))
        self.write({'line_ids': [Command.clear()] + lines, 'step': 'check'})
        return self._om_qa_action(self.env._("Paste lines"))

    def action_back(self):
        self.write({'line_ids': [Command.clear()], 'step': 'paste'})
        return self._om_qa_action(self.env._("Paste lines"))

    def action_add(self):
        self.ensure_one()
        items = [{
            'product': line.product_id,
            'quantity': line.quantity,
            'price_unit': line.price_unit if line.has_price else None,
        } for line in self.line_ids if line.product_id and line.quantity > 0]
        return self._om_qa_add_and_close(items)


class OmQuickAddPasteLine(models.TransientModel):
    _name = 'om.quick.add.paste.line'
    _description = 'Pasted Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('om.quick.add.paste', required=True, ondelete='cascade')
    sequence = fields.Integer()
    row = fields.Char(string="Pasted", readonly=True)
    product_id = fields.Many2one('product.product', string="Product")
    candidate_ids = fields.Many2many('product.product', 'om_quick_add_paste_line_candidate_rel',
                                     'line_id', 'product_id', string="Possible products")
    quantity = fields.Float(digits='Product Unit', default=1.0)
    price_unit = fields.Float(string="Price", digits="Product Price",
                              help="The price pasted; when none, the price of the document applies.")
    has_price = fields.Boolean(string="Pasted price")
    state = fields.Selection([('found', "Found"), ('choose', "Choose"), ('missing', "Not found")],
                             compute='_compute_state')

    @api.depends('product_id', 'candidate_ids')
    def _compute_state(self):
        for line in self:
            line.state = 'found' if line.product_id else 'choose' if line.candidate_ids else 'missing'

    @api.onchange('price_unit')
    def _onchange_price_unit(self):
        self.has_price = True
