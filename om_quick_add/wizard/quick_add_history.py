from odoo import api, fields, models
from odoo.fields import Command


class OmQuickAddHistory(models.TransientModel):
    _name = 'om.quick.add.history'
    _inherit = 'om.quick.add.wizard'
    _description = 'Products Bought or Supplied Before'

    partner_id = fields.Many2one('res.partner', readonly=True)
    keep_prices = fields.Boolean(string="Use the last prices",
                                 help="Add the products at the price of their last line instead of today's price.")
    line_ids = fields.One2many('om.quick.add.history.line', 'wizard_id')
    last_document_ref = fields.Reference(selection='_selection_documents', readonly=True)

    @api.model
    def _selection_documents(self):
        return self.env['om.quick.add.mixin']._om_qa_copy_models()

    def _om_qa_load(self):
        document = self._om_qa_document()
        entries = document._om_qa_history()
        lines = [Command.create({
            'product_id': entry['product'].id,
            'uom_id': entry['uom'].id,
            'last_date': entry['date'],
            'last_document_ref': '%s,%s' % (entry['document']._name, entry['document'].id),
            'last_quantity': entry['quantity'],
            'last_price': entry.get('price_unit') or 0.0,
            'last_discount': entry.get('discount') or 0.0,
            'count': entry['count'],
            'total': entry['total'],
        }) for entry in entries]
        last = entries[0]['document'] if entries else False
        self.write({
            'partner_id': document._om_qa_partner().id,
            'line_ids': lines,
            'last_document_ref': '%s,%s' % (last._name, last.id) if last else False,
        })

    def _om_qa_items(self, lines):
        return [{
            'product': line.product_id,
            'quantity': line.quantity,
            'uom': line.uom_id,
            'price_unit': line.last_price if self.keep_prices else None,
            'discount': line.last_discount if self.keep_prices else None,
        } for line in lines if line.quantity > 0]

    def action_fill_last(self):
        for line in self.line_ids:
            line.quantity = line.last_quantity
        return self._om_qa_action(self.env._("History of %s", self.partner_id.display_name))

    def action_add(self):
        self.ensure_one()
        return self._om_qa_add_and_close(self._om_qa_items(self.line_ids))

    def action_repeat_last(self):
        """Every line of the last document of the partner, at its quantity."""
        self.ensure_one()
        last = self.last_document_ref
        if not last:
            return self._om_qa_action(self.env._("History of %s", self.partner_id.display_name))
        items = [{
            'product': data['product'],
            'quantity': data['quantity'],
            'uom': data['uom'],
            'price_unit': data.get('price_unit') if self.keep_prices else None,
            'discount': data.get('discount') if self.keep_prices else None,
        } for data in map(last._om_qa_line_data, last._om_qa_lines())]
        return self._om_qa_add_and_close(items)


class OmQuickAddHistoryLine(models.TransientModel):
    _name = 'om.quick.add.history.line'
    _description = 'Product Bought or Supplied Before'
    _order = 'last_date desc, id'

    wizard_id = fields.Many2one('om.quick.add.history', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Product", readonly=True)
    uom_id = fields.Many2one('uom.uom', string="Unit", readonly=True)
    last_date = fields.Date(string="Last", readonly=True)
    last_document_ref = fields.Reference(selection='_selection_documents', string="Document", readonly=True)
    last_quantity = fields.Float(string="Last Qty", digits='Product Unit', readonly=True)
    last_price = fields.Float(string="Last Price", digits='Product Price', readonly=True)
    last_discount = fields.Float(string="Last Disc. %", digits='Discount', readonly=True)
    count = fields.Integer(string="Times", readonly=True)
    total = fields.Float(string="Total Qty", digits='Product Unit', readonly=True)
    quantity = fields.Float(string="Add", digits='Product Unit')

    @api.model
    def _selection_documents(self):
        return self.env['om.quick.add.mixin']._om_qa_copy_models()
