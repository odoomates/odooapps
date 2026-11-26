from odoo import api, fields, models
from odoo.fields import Command


class OmQuickAddCopy(models.TransientModel):
    _name = 'om.quick.add.copy'
    _inherit = 'om.quick.add.wizard'
    _description = 'Copy Lines'

    source_model = fields.Selection(selection='_selection_documents', string="Document type")
    source_id = fields.Many2oneReference(model_field='source_model', string="Copy from")
    several_models = fields.Boolean(compute='_compute_several_models')
    keep_prices = fields.Boolean(string="Keep the prices",
                                 help="Add the lines at the price of the document copied instead of today's price.")
    line_ids = fields.One2many('om.quick.add.copy.line', 'wizard_id')

    @api.model
    def _selection_documents(self):
        return self.env['om.quick.add.mixin']._om_qa_copy_models()

    def _compute_several_models(self):
        several = len(self._selection_documents()) > 1
        for wizard in self:
            wizard.several_models = several

    def _om_qa_load(self):
        self.source_model = self.res_model

    @api.onchange('source_model')
    def _onchange_source_model(self):
        self.source_id = False

    @api.onchange('source_model', 'source_id')
    def _onchange_source_id(self):
        commands = [Command.clear()]
        source = self.env[self.source_model].browse(self.source_id) if self.source_model and self.source_id else False
        if source and source == self._om_qa_document():
            self.source_id = False
            self.line_ids = commands
            return {'warning': {'title': self.env._("Copy lines"),
                                'message': self.env._("This is the document itself: pick another one.")}}
        if source:
            for data in map(source._om_qa_line_data, source._om_qa_lines()):
                commands.append(Command.create({
                    'product_id': data['product'].id,
                    'uom_id': data['uom'].id,
                    'source_quantity': data['quantity'],
                    'quantity': data['quantity'],
                    'price_unit': data.get('price_unit') or 0.0,
                    'discount': data.get('discount') or 0.0,
                }))
        self.line_ids = commands

    def action_add(self):
        self.ensure_one()
        items = [{
            'product': line.product_id,
            'quantity': line.quantity,
            'uom': line.uom_id if line.uom_id and line.uom_id._has_common_reference(line.product_id.uom_id)
            else None,
            'price_unit': line.price_unit if self.keep_prices else None,
            'discount': line.discount if self.keep_prices else None,
        } for line in self.line_ids if line.product_id and line.quantity > 0]
        return self._om_qa_add_and_close(items)


class OmQuickAddCopyLine(models.TransientModel):
    _name = 'om.quick.add.copy.line'
    _description = 'Line to Copy'

    wizard_id = fields.Many2one('om.quick.add.copy', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Product", readonly=True)
    uom_id = fields.Many2one('uom.uom', string="Unit", readonly=True)
    source_quantity = fields.Float(string="Quantity", digits='Product Unit', readonly=True)
    quantity = fields.Float(string="Add", digits='Product Unit')
    price_unit = fields.Float(string="Price", digits='Product Price', readonly=True)
    discount = fields.Float(string="Disc. %", digits='Discount', readonly=True)
