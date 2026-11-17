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
METAFIELD_TYPES = [
    ('single_line_text_field', 'Single line text'),
    ('multi_line_text_field', 'Multi-line text'),
    ('number_integer', 'Integer'),
    ('number_decimal', 'Decimal'),
    ('boolean', 'True or false'),
    ('date', 'Date'),
    ('date_time', 'Date and time'),
    ('json', 'JSON'),
]


class OmShopifyMetafield(models.Model):
    """ A Shopify metafield and the Odoo field it fills, or is filled from. """
    _name = 'om.shopify.metafield'
    _description = 'Shopify Metafield Mapping'
    _order = 'store_id, resource, namespace, key'

    store_id = fields.Many2one('om.shopify.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    active = fields.Boolean(default=True)
    resource = fields.Selection([
        ('product', 'Product'),
        ('variant', 'Variant'),
        ('customer', 'Customer'),
        ('order', 'Order'),
    ], required=True, default='product')
    model_name = fields.Char(compute='_compute_model_name')
    namespace = fields.Char(required=True, default='custom')
    key = fields.Char(required=True)
    metafield_type = fields.Selection(METAFIELD_TYPES, string='Shopify Type', required=True,
                                      default='single_line_text_field')
    field_id = fields.Many2one('ir.model.fields', string='Odoo Field', required=True, ondelete='cascade',
                               domain="[('model', '=', model_name), ('ttype', 'in', %s), ('store', '=', True)]"
                               % FIELD_TYPES)
    direction = fields.Selection([
        ('import', 'Shopify → Odoo'),
        ('export', 'Odoo → Shopify'),
        ('both', 'Both Ways'),
    ], required=True, default='import',
        help="Odoo → Shopify is for products and variants: their metafields are sent with the product export.")

    _store_key_unique = models.Constraint('unique (store_id, resource, namespace, key)',
                                          "A metafield is mapped once per store.")

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
                raise ValidationError(_("%(field)s cannot hold a metafield.", field=mapping.field_id.name))
            if mapping.direction != 'import' and mapping.resource not in ('product', 'variant'):
                raise ValidationError(_("Only the metafields of products and variants are sent to Shopify."))

    @property
    def full_key(self):
        return f'{self.namespace}.{self.key}'

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _to_odoo(self, value):
        self.ensure_one()
        ttype = self.field_id.ttype
        if value in (None, ''):
            return False
        try:
            if ttype in ('integer',):
                return int(float(value))
            if ttype in ('float', 'monetary'):
                return float(json.loads(value)['amount']) if value.startswith('{') else float(value)
            if ttype == 'boolean':
                return str(value).lower() == 'true'
            if ttype == 'date':
                return fields.Date.to_date(value[:10])
            if ttype == 'datetime':
                return fields.Datetime.to_datetime(value[:19].replace('T', ' '))
            if ttype == 'selection':
                record = self.env[self.field_id.model]
                keys = [k for k, _label in record._fields[self.field_id.name]._description_selection(self.env)]
                return value if value in keys else False
        except (ValueError, TypeError, KeyError):
            return False
        return value

    def _to_shopify(self, value):
        self.ensure_one()
        if value is False or value is None or value == '':
            return None
        if self.field_id.ttype == 'boolean':
            return 'true' if value else 'false'
        if self.field_id.ttype in ('date', 'datetime'):
            return fields.Date.to_string(value) if self.field_id.ttype == 'date' \
                else fields.Datetime.to_datetime(value).strftime('%Y-%m-%dT%H:%M:%SZ')
        return str(value)


class OmShopifyStoreMetafields(models.Model):
    _inherit = 'om.shopify.store'

    metafield_ids = fields.One2many('om.shopify.metafield', 'store_id', string='Metafields')

    def _shopify_metafield_maps(self, resource, direction=('import', 'both')):
        self.ensure_one()
        return self.metafield_ids.filtered(lambda m: m.resource == resource and m.direction in direction)

    def _shopify_query(self, query, bulk=False):
        """ ``query`` with the mapped metafields of each resource in place of its ``# om:metafields:…``
        comment. Without mappings the comment stays, and costs nothing. """
        self.ensure_one()
        for resource in RESOURCE_MODELS:
            marker = f'# om:metafields:{resource}'
            maps = self._shopify_metafield_maps(resource, ('import', 'both', 'export'))
            if marker not in query or not maps:
                continue
            keys = ', '.join(json.dumps(m.full_key) for m in maps)
            node = 'id namespace key value type'
            selection = (f'metafields(keys: [{keys}]) {{ edges {{ node {{ {node} }} }} }}' if bulk
                         else f'metafields(first: 50, keys: [{keys}]) {{ nodes {{ {node} }} }}')
            query = query.replace(marker, selection)
        return query

    def _shopify_apply_metafields(self, resource, record, metafields):
        """ Write the mapped metafields of ``metafields`` (a connection, or a list) on ``record``. """
        self.ensure_one()
        maps = self._shopify_metafield_maps(resource)
        if not maps or not record:
            return
        if isinstance(metafields, dict):
            metafields = metafields.get('nodes') or [e.get('node') for e in metafields.get('edges') or []]
        values = {f"{m.get('namespace')}.{m.get('key')}": m.get('value') for m in metafields or [] if m}
        vals = {mapping.field_id.name: mapping._to_odoo(values[mapping.full_key])
                for mapping in maps if mapping.full_key in values}
        if vals:
            record.sudo().write(vals)

    def _shopify_metafield_inputs(self, resource, record):
        """ The metafields of ``record`` to send with a product export. """
        self.ensure_one()
        inputs = []
        for mapping in self._shopify_metafield_maps(resource, ('export', 'both')):
            value = mapping._to_shopify(record[mapping.field_id.name])
            if value is not None:
                inputs.append({'namespace': mapping.namespace, 'key': mapping.key,
                               'type': mapping.metafield_type, 'value': value})
        return inputs
