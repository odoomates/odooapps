import re

from odoo import api, fields, models
from odoo.fields import Command

from ..models.quick_add_mixin import parse_number

SEPARATOR_TOKENS = {'x', 'X', '×', '*', ':', '=', '-'}


def split_cells(row):
    """The cells of a row copied from a spreadsheet (tabs) or written as a list (semicolons, commas
    between words); None for a row of words and numbers separated by spaces."""
    if '\t' in row:
        cells = row.split('\t')
    elif ';' in row:
        cells = row.split(';')
    elif re.search(r',\s*\D|\D\s*,', row):
        cells = row.split(',')
    else:
        return None
    return [cell.strip() for cell in cells if cell.strip()]


def row_candidates(row):
    """The ways to read a row, as [(reference, quantity, price)], the one with the most numbers first."""
    cells = split_cells(row)
    if cells is not None:
        if not cells:
            return []
        numbers = [parse_number(cell) for cell in cells]
        ref_index = next((i for i, number in enumerate(numbers) if number is None), 0)
        before = [n for n in numbers[:ref_index] if n is not None]
        after = [n for n in numbers[ref_index + 1:] if n is not None]
        quantity = (after[:1] or before[:1] or [None])[0]
        price = after[1] if len(after) > 1 else None
        return [(cells[ref_index], quantity, price)]
    tokens = row.split()
    candidates = []
    # numbers at the end: quantity, then price
    trailing = 0
    while trailing < min(2, len(tokens) - 1) and parse_number(tokens[-1 - trailing]) is not None:
        trailing += 1
    for count in range(trailing, -1, -1):
        ref_tokens = tokens[:len(tokens) - count]
        while len(ref_tokens) > 1 and ref_tokens[-1] in SEPARATOR_TOKENS:
            ref_tokens = ref_tokens[:-1]
        numbers = [parse_number(t) for t in tokens[len(tokens) - count:]]
        candidates.append((' '.join(ref_tokens), numbers[0] if numbers else None,
                           numbers[1] if len(numbers) > 1 else None))
    # a quantity first: "5 Desk", "5 x Desk", "5x Desk"
    match = re.match(r'^(\d[\d.,]*)\s*(?:[xX×*]\s+|\s+)(.*\D.*)$', row)
    if match and parse_number(match.group(1)) is not None:
        candidates.append((match.group(2).strip(), parse_number(match.group(1)), None))
    return candidates


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
        """{'row', 'product_id', 'candidate_ids', 'quantity', 'price_unit', 'has_price'} of a row: the reading
        that designates one product, else the first that finds some, else the first."""
        candidates = row_candidates(row)
        if not candidates:
            return None
        readings = []
        for ref, quantity, price in candidates:
            products = document._om_qa_find_products(ref)
            readings.append((ref, quantity, price, products))
            if len(products) == 1:
                break
        chosen = next((r for r in readings if len(r[3]) == 1), None) \
            or next((r for r in readings if r[3]), None) or readings[0]
        ref, quantity, price, products = chosen
        return {
            'row': row.strip(),
            'product_id': products.id if len(products) == 1 else False,
            'candidate_ids': [Command.set(products.ids if len(products) > 1 else [])],
            'quantity': quantity if quantity and quantity > 0 else 1.0,
            'price_unit': price or 0.0,
            'has_price': price is not None,
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
