import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

RESOURCE_MODELS = {
    'product': 'product.template',
    'variant': 'product.product',
    'customer': 'res.partner',
    'order': 'sale.order',
}
FIELD_TYPES = ['char', 'text', 'html', 'integer', 'float', 'monetary', 'boolean', 'date', 'datetime', 'selection']


class OmWoocommerceMeta(models.Model):
    """ A meta data key of WooCommerce and the Odoo field it fills, or is filled from. """
    _name = 'om.woocommerce.meta'
    _description = 'WooCommerce Meta Data Mapping'
    _order = 'store_id, resource, key'

    store_id = fields.Many2one('om.woocommerce.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    active = fields.Boolean(default=True)
    resource = fields.Selection([
        ('product', 'Product'),
        ('variant', 'Variation'),
        ('customer', 'Customer'),
        ('order', 'Order'),
    ], required=True, default='product')
    model_name = fields.Char(compute='_compute_model_name')
    key = fields.Char(required=True, help="The meta key in WooCommerce, e.g. _brand or _wc_gla_mpn.")
    field_id = fields.Many2one('ir.model.fields', string='Odoo Field', required=True, ondelete='cascade',
                               domain="[('model', '=', model_name), ('ttype', 'in', %s), ('store', '=', True)]"
                               % FIELD_TYPES)
    direction = fields.Selection([
        ('import', 'WooCommerce → Odoo'),
        ('export', 'Odoo → WooCommerce'),
        ('both', 'Both Ways'),
    ], required=True, default='import',
        help="Odoo → WooCommerce is for products and variations: their meta data is sent with the product export.")

    _sql_constraints = [
        ('store_key_unique', 'unique (store_id, resource, key)',
         "A meta key is mapped once per store."),
    ]

    @api.depends('resource')
    def _compute_model_name(self):
        for mapping in self:
            mapping.model_name = RESOURCE_MODELS.get(mapping.resource)

    @api.constrains('field_id', 'resource', 'direction')
    def _check_field(self):
        for mapping in self:
            if mapping.field_id.model != RESOURCE_MODELS[mapping.resource]:
                raise ValidationError(_("The field of %(key)s is not a field of the %(resource)s.",
                                        key=mapping.key, resource=mapping.resource))
            if mapping.field_id.ttype not in FIELD_TYPES:
                raise ValidationError(_("%(field)s cannot hold a meta value.", field=mapping.field_id.name))
            if mapping.direction != 'import' and mapping.resource not in ('product', 'variant'):
                raise ValidationError(_("Only the meta data of products and variations is sent to WooCommerce."))

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _to_odoo(self, value):
        """ A meta value of WooCommerce (any JSON) as a value of the Odoo field; False when it does
        not fit. """
        self.ensure_one()
        ttype = self.field_id.ttype
        if value in (None, '', [], {}):
            return False
        try:
            if ttype == 'integer':
                return int(float(value))
            if ttype in ('float', 'monetary'):
                return float(value)
            if ttype == 'boolean':
                return value is True or str(value).lower() in ('1', 'true', 'yes', 'on')
            if ttype == 'date':
                return fields.Date.to_date(str(value)[:10])
            if ttype == 'datetime':
                return fields.Datetime.to_datetime(str(value)[:19].replace('T', ' '))
            if ttype == 'selection':
                record = self.env[self.field_id.model]
                keys = [k for k, _label in record._fields[self.field_id.name]._description_selection(self.env)]
                return value if value in keys else False
        except (ValueError, TypeError):
            return False
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)

    def _to_woo(self, value):
        """ The value of the Odoo field for WooCommerce; None when empty. """
        self.ensure_one()
        ttype = self.field_id.ttype
        if value is None or (value is False and ttype != 'boolean') or value == '':
            return None
        if ttype == 'boolean':
            return 'yes' if value else 'no'
        if ttype == 'date':
            return fields.Date.to_string(value)
        if ttype == 'datetime':
            return fields.Datetime.to_datetime(value).strftime('%Y-%m-%dT%H:%M:%S')
        if ttype in ('integer', 'float', 'monetary'):
            return value
        return str(value)


class OmWoocommerceStoreMeta(models.Model):
    _inherit = 'om.woocommerce.store'

    meta_ids = fields.One2many('om.woocommerce.meta', 'store_id', string='Meta Data')

    def _woo_meta_maps(self, resource, direction=('import', 'both')):
        self.ensure_one()
        return self.meta_ids.filtered(lambda m: m.resource == resource and m.direction in direction)

    def _woo_apply_meta(self, resource, record, meta_data):
        """ Write the mapped keys of ``meta_data`` (``[{key, value}]``) on ``record``. """
        self.ensure_one()
        maps = self._woo_meta_maps(resource)
        if not maps or not record:
            return
        values = {m.get('key'): m.get('value') for m in meta_data or [] if isinstance(m, dict)}
        vals = {mapping.field_id.name: mapping._to_odoo(values[mapping.key])
                for mapping in maps if mapping.key in values}
        if vals:
            record.sudo().write(vals)

    def _woo_meta_values(self, resource, record):
        """ The ``meta_data`` of ``record`` to send with a product export. """
        self.ensure_one()
        meta = []
        for mapping in self._woo_meta_maps(resource, ('export', 'both')):
            value = mapping._to_woo(record[mapping.field_id.name])
            if value is not None:
                meta.append({'key': mapping.key, 'value': value})
        return meta
