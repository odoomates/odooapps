import base64
import csv
import io

from odoo import _, fields, models
from odoo.exceptions import UserError

HEADERS = ['woocommerce_id', 'odoo_reference', 'odoo_barcode']


class OmWoocommerceMappingWizard(models.TransientModel):
    """ Link WooCommerce products and variations to Odoo products from a CSV or Excel file: for
    catalogues whose SKUs or GTINs do not match. """
    _name = 'om.woocommerce.mapping.wizard'
    _description = 'Map WooCommerce Products to Odoo Products'

    store_id = fields.Many2one('om.woocommerce.store', required=True, domain="[('state', '=', 'connected')]")
    file = fields.Binary(required=True)
    filename = fields.Char()
    template_file = fields.Binary(compute='_compute_template_file')
    template_filename = fields.Char(compute='_compute_template_file')

    def _compute_template_file(self):
        content = ','.join(HEADERS) + '\n123,MUG-1,\n'
        for wizard in self:
            wizard.template_file = base64.b64encode(content.encode())
            wizard.template_filename = 'woocommerce_mapping.csv'

    def _rows(self):
        content = base64.b64decode(self.file)
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
        if 'woocommerce_id' not in header or not ({'odoo_reference', 'odoo_barcode'} & set(header)):
            raise UserError(_("The file needs the columns %(columns)s.", columns=', '.join(HEADERS)))
        return [dict(zip(header, row)) for row in rows[1:] if any(row)]

    def action_map(self):
        self.ensure_one()
        store = self.store_id
        Product = self.env['product.product'].with_context(active_test=False)
        Template = self.env['om.woocommerce.product.template']
        Variant = self.env['om.woocommerce.product']
        errors, count = [], 0
        for number, row in enumerate(self._rows(), 2):
            ref, barcode = row.get('odoo_reference'), row.get('odoo_barcode')
            product = Product.search([('default_code', '=', ref)], limit=2) if ref else Product.browse()
            if not product and barcode:
                product = Product.search([('barcode', '=', barcode)], limit=2)
            if len(product) != 1:
                errors.append(_("Line %(line)s: no single Odoo product %(ref)s", line=number, ref=ref or barcode))
                continue
            woo_id = row.get('woocommerce_id', '').split('.')[0]
            data = store._woo_get(f'products/{woo_id}') if woo_id.isdigit() else None
            if not data:
                errors.append(_("Line %(line)s: no WooCommerce product %(id)s", line=number, id=woo_id))
                continue
            parent = store._woo_get(f"products/{data['parent_id']}") if data.get('parent_id') else data
            template_binding = Template._connector_bind(store, str(parent['id']), product.product_tmpl_id, {
                'name': parent.get('name'), 'slug': parent.get('slug'), 'woo_type': parent.get('type')
                if parent.get('type') in ('simple', 'variable') else False, 'active': True})
            values = Template._woo_variant_values(data, parent, parent=bool(data.get('parent_id')))
            Variant._woo_bind_variant(store, template_binding, values, product)
            count += 1
        message = _("%(count)s product(s) linked.", count=count)
        if errors:
            message += '\n' + '\n'.join(errors)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'message': message, 'type': 'warning' if errors else 'success', 'sticky': bool(errors),
                       'next': {'type': 'ir.actions.act_window_close'}},
        }
