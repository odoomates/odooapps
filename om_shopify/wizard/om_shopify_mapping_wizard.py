import csv
import io

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

from ..tools import queries

HEADERS = ['shopify_variant_id', 'odoo_reference', 'odoo_barcode']


class OmShopifyMappingWizard(models.TransientModel):
    """ Link Shopify variants to Odoo products from a CSV or Excel file: for catalogues whose SKUs
    or barcodes do not match. """
    _name = 'om.shopify.mapping.wizard'
    _description = 'Map Shopify Variants to Odoo Products'

    store_id = fields.Many2one('om.shopify.store', required=True, domain="[('state', '=', 'connected')]")
    file = fields.Binary(required=True)
    filename = fields.Char()
    template_file = fields.Binary(compute='_compute_template_file')

    def _compute_template_file(self):
        content = ','.join(HEADERS) + '\n1234567890,MUG-1,\n'
        for wizard in self:
            wizard.template_file = BinaryBytes(content.encode(), filename='shopify_mapping.csv')

    def _rows(self):
        content = bytes(self.file)
        name = (self.filename or '').lower()
        if name.endswith(('.xlsx', '.xls')):
            try:
                import openpyxl
            except ImportError as e:
                raise UserError(_("Reading Excel files needs the Python library openpyxl.")) from e
            sheet = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True).active
            rows = [[('' if c is None else str(c)).strip() for c in row] for row in sheet.iter_rows(values_only=True)]
        else:
            text = content.decode('utf-8-sig')
            rows = [[c.strip() for c in row] for row in csv.reader(io.StringIO(text))]
        if not rows:
            raise UserError(_("The file is empty."))
        header = [h.lower() for h in rows[0]]
        if 'shopify_variant_id' not in header or not ({'odoo_reference', 'odoo_barcode'} & set(header)):
            raise UserError(_("The file needs the columns %(columns)s.", columns=', '.join(HEADERS)))
        return [dict(zip(header, row)) for row in rows[1:] if any(row)]

    def action_map(self):
        self.ensure_one()
        store = self.store_id
        Product = self.env['product.product'].with_context(active_test=False)
        Template = self.env['om.shopify.product.template']
        Variant = self.env['om.shopify.product']
        errors, count = [], 0
        for number, row in enumerate(self._rows(), 2):
            ref, barcode = row.get('odoo_reference'), row.get('odoo_barcode')
            product = Product.search([('default_code', '=', ref)], limit=2) if ref else Product.browse()
            if not product and barcode:
                product = Product.search([('barcode', '=', barcode)], limit=2)
            if len(product) != 1:
                errors.append(_("Line %(line)s: no single Odoo product %(ref)s", line=number, ref=ref or barcode))
                continue
            raw = row.get('shopify_variant_id', '').split('.')[0]
            gid = raw if raw.startswith('gid://') else f'gid://shopify/ProductVariant/{raw}'
            variant = store._shopify_execute(queries.VARIANT, {'id': gid}).get('productVariant')
            if not variant:
                errors.append(_("Line %(line)s: no Shopify variant %(id)s", line=number, id=raw))
                continue
            shopify_product = variant['product']
            template_binding = Template._connector_bind(store, shopify_product['id'], product.product_tmpl_id, {
                'name': shopify_product['title'], 'handle': shopify_product.get('handle'),
                'shopify_status': shopify_product.get('status'), 'active': True})
            Variant._shopify_bind_variant(store, template_binding, variant, product)
            count += 1
        message = _("%(count)s variant(s) linked.", count=count)
        if errors:
            message += '\n' + '\n'.join(errors)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'message': message, 'type': 'warning' if errors else 'success', 'sticky': bool(errors),
                       'next': {'type': 'ir.actions.act_window_close'}},
        }
