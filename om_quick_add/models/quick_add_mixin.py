import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.tools import float_compare
from odoo.tools.sql import escape_like_value

SEARCH_LIMIT = 8
HISTORY_LINES = 2000
HISTORY_PRODUCTS = 300


def clean_context(context):
    """Only the user's settings of a context: the list of lines of a form gives its buttons the defaults
    and the views of a new line and other keys of its own, which must not reach the dialogs nor the
    lines they add."""
    return {key: context[key] for key in ('lang', 'tz', 'uid', 'allowed_company_ids') if key in context}


def parse_number(text):
    """A quantity or a price as people type it: 2, 2.5, 2,5, 1,250.00, 1.250,00 or 1 250; None if it is not
    a number. A lone comma is a decimal comma."""
    text = re.sub(r"[\s\u00a0\u202f']", '', text or '')
    if not re.fullmatch(r'-?\d+(?:[.,]\d+)*', text):
        return None
    if ',' in text and '.' in text:
        decimal = ',' if text.rfind(',') > text.rfind('.') else '.'
        text = text.replace('.' if decimal == ',' else ',', '').replace(decimal, '.')
    elif text.count(',') > 1 or text.count('.') > 1:
        text = text.replace(',', '').replace('.', '')
    else:
        text = text.replace(',', '.')
    return float(text)


class OmQuickAddMixin(models.AbstractModel):
    """Quick ways to add products to a document with lines: paste a list, scan barcodes, the history of
    the partner, the lines of another document. A document inherits this mixin and says where its
    lines are and how a line is made."""
    _name = 'om.quick.add.mixin'
    _description = 'Quick Add Products'

    # the lines of the document and their quantity field
    _om_qa_line_field = False
    _om_qa_quantity_field = False
    # whether the lines have a price
    _om_qa_has_prices = True

    om_quick_add_ok = fields.Boolean(compute='_compute_om_quick_add_ok')

    def _compute_om_quick_add_ok(self):
        for record in self:
            record.om_quick_add_ok = record._om_qa_editable()

    # ------------------------------------------------------------------
    # What a document says
    # ------------------------------------------------------------------

    def _om_qa_editable(self):
        """Whether lines may be added."""
        return True

    def _om_qa_partner(self):
        """The customer or vendor whose history is shown."""
        return self.env['res.partner']

    def _om_qa_product_domain(self):
        """The products the document may take."""
        return Domain('company_id', 'in', [False, self.company_id.id])

    def _om_qa_code_domain(self, code):
        """Other references of a product for this document, such as the code of the vendor; None if none."""
        return None

    def _om_qa_lines(self):
        """The product lines of the document."""
        raise NotImplementedError()

    def _om_qa_line_data(self, line):
        """{'product', 'quantity', 'uom', 'price_unit', 'discount', 'date', 'document'} of a line, of this
        document or of another one of the same kind."""
        raise NotImplementedError()

    def _om_qa_new_line_vals(self, product, quantity, uom, price_unit, discount):
        """The values of a new line; uom, price_unit and discount may be None: the defaults apply."""
        raise NotImplementedError()

    def _om_qa_history_lines(self):
        """The lines of the earlier documents of the partner, of the kind of this one."""
        return self.env[self._fields[self._om_qa_line_field].comodel_name]

    # ------------------------------------------------------------------
    # Finding products
    # ------------------------------------------------------------------

    def _om_qa_exact_domains(self, ref):
        domains = [Domain('barcode', '=', ref), Domain('default_code', '=ilike', escape_like_value(ref))]
        code_domain = self._om_qa_code_domain(ref)
        if code_domain is not None:
            domains.append(code_domain)
        return domains

    def _om_qa_find_products(self, ref, exact_only=False):
        """The products a reference designates: by barcode, internal reference or another code first,
        then by name; several when it is ambiguous, none when nothing matches."""
        ref = (ref or '').strip()
        if not ref:
            return self.env['product.product']
        Product = self.env['product.product']
        base = Domain(self._om_qa_product_domain())
        for domain in self._om_qa_exact_domains(ref):
            products = Product.search(base & domain, limit=SEARCH_LIMIT)
            if products:
                return products
        if exact_only:
            return Product
        products = Product.search(base & Domain('name', '=ilike', escape_like_value(ref)), limit=SEARCH_LIMIT)
        if products:
            return products
        return Product.search(base & (Domain('name', 'ilike', ref) | Domain('default_code', 'ilike', ref)),
                              limit=SEARCH_LIMIT)

    # ------------------------------------------------------------------
    # Adding lines
    # ------------------------------------------------------------------

    def _om_qa_check_editable(self):
        for record in self:
            if not record._om_qa_editable():
                raise UserError(_("Products can no longer be added to %s.", record.display_name))

    def _om_qa_same(self, value, other, digits='Product Price'):
        if value is None:
            return True
        precision = self.env['decimal.precision'].precision_get(digits)
        return not float_compare(value or 0.0, other or 0.0, precision_digits=precision)

    def _om_qa_add(self, items):
        """Add products: items are {'product', 'quantity'} with optional 'uom', 'price_unit' and
        'discount'. A product already on the document, in the same unit and at the same price, gets its
        quantity raised instead of a second line. Returns (lines added, lines raised)."""
        self.ensure_one()
        self._om_qa_check_editable()
        # the same product twice in the items: one line
        merged = {}
        for item in items:
            product = item.get('product')
            quantity = item.get('quantity') or 0.0
            if not product or quantity <= 0:
                continue
            uom = item.get('uom') or None
            price = item.get('price_unit') if self._om_qa_has_prices else None
            discount = item.get('discount') if self._om_qa_has_prices else None
            key = (product.id, uom and uom.id, price, discount)
            if key in merged:
                merged[key]['quantity'] += quantity
            else:
                merged[key] = {'product': product, 'quantity': quantity, 'uom': uom, 'price_unit': price,
                               'discount': discount}
        lines = [(line, self._om_qa_line_data(line)) for line in self._om_qa_lines()]
        quantities = {}
        creates = []
        prices = []
        for item in merged.values():
            match = next((line for line, data in lines
                          if data['product'] == item['product']
                          and (item['uom'] is None or data['uom'] == item['uom'])
                          and self._om_qa_same(item['price_unit'], data.get('price_unit'))
                          and self._om_qa_same(item['discount'], data.get('discount'), 'Discount')), None)
            if match:
                quantities[match.id] = quantities.get(match.id, match[self._om_qa_quantity_field]) + item['quantity']
            else:
                creates.append(Command.create(self._om_qa_new_line_vals(
                    item['product'], item['quantity'], item['uom'], None, None)))
                prices.append(self._om_qa_price_vals(item['price_unit'], item['discount']))
        commands = [Command.update(line_id, {self._om_qa_quantity_field: quantity})
                    for line_id, quantity in quantities.items()] + creates
        if commands:
            before = set(self._om_qa_lines().ids)
            self.write({self._om_qa_line_field: commands})
            # the prices given are written after the lines are made, as a user types them: kept as
            # set by hand, not computed again when the quantity changes
            new_lines = sorted(set(self._om_qa_lines().ids) - before)
            updates = [Command.update(line_id, vals) for line_id, vals in zip(new_lines, prices) if vals]
            if updates:
                self.write({self._om_qa_line_field: updates})
        return len(creates), len(quantities)

    def _om_qa_price_vals(self, price_unit, discount):
        """The values of a price and a discount given for a new line; None for the default."""
        vals = {}
        if price_unit is not None:
            vals['price_unit'] = price_unit
        if discount is not None:
            vals['discount'] = discount
        return vals

    def om_quick_add_scan(self, barcode):
        """A scanned barcode: the product added, or its quantity raised by one."""
        self.ensure_one()
        products = self._om_qa_find_products(barcode, exact_only=True)
        if not products:
            return {'type': 'warning', 'message': _("No product with the barcode or reference %s.", barcode)}
        if len(products) > 1:
            return {'type': 'warning',
                    'message': _("Several products have the barcode or reference %s.", barcode)}
        added, _raised = self._om_qa_add([{'product': products, 'quantity': 1.0}])
        message = _("%s added.", products.display_name) if added else _("%s: one more.", products.display_name)
        return {'type': 'success', 'message': message}

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _om_qa_history(self):
        """[{'product', 'uom', 'date', 'document', 'quantity', 'price_unit', 'discount', 'count',
        'total'}] per product (and unit) the partner had, the latest first."""
        self.ensure_one()
        if not self._om_qa_partner():
            return []
        result = {}
        for line in self._om_qa_history_lines()[:HISTORY_LINES]:
            data = self._om_qa_line_data(line)
            key = (data['product'].id, data['uom'].id)
            entry = result.get(key)
            if entry is None:
                entry = result[key] = {**data, 'count': 0, 'total': 0.0, 'documents': set()}
            elif data['date'] and (not entry['date'] or data['date'] > entry['date']):
                entry.update({k: data[k] for k in ('date', 'document', 'quantity', 'price_unit', 'discount')})
            entry['documents'].add(data['document'].id)
            entry['total'] += data['quantity']
        entries = list(result.values())
        for entry in entries:
            entry['count'] = len(entry.pop('documents'))
        entries.sort(key=lambda e: (e['date'] or fields.Date.to_date('1900-01-01'), e['document'].id), reverse=True)
        return entries[:HISTORY_PRODUCTS]

    # ------------------------------------------------------------------
    # Copy lines
    # ------------------------------------------------------------------

    @api.model
    def _om_qa_copy_models(self):
        """[(model, label)] of the documents lines can be copied from."""
        mixin = self.pool['om.quick.add.mixin']
        models_ = [(name, self.env[name]._om_qa_copy_label()) for name, cls in self.pool.items()
                   if not cls._abstract and not cls._transient and issubclass(cls, mixin)]
        return sorted(models_, key=lambda m: m[1])

    @api.model
    def _om_qa_copy_label(self):
        """The name of the documents in the Copy lines picker."""
        return self.env['ir.model']._get(self._name).name

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _om_qa_open(self, wizard_model, title):
        self.ensure_one()
        self._om_qa_check_editable()
        wizard = self.env[wizard_model].create({'res_model': self._name, 'res_id': self.id})
        wizard._om_qa_load()
        return wizard._om_qa_action(title)

    def om_action_quick_paste(self):
        return self._om_qa_open('om.quick.add.paste', _("Paste lines"))

    def om_action_quick_history(self):
        self.ensure_one()
        return self._om_qa_open('om.quick.add.history', _("History of %s", self._om_qa_partner().display_name))

    def om_action_quick_copy(self):
        return self._om_qa_open('om.quick.add.copy', _("Copy lines"))


class OmQuickAddLineMixin(models.AbstractModel):
    """The lines of a document: the Quick Add buttons of the list of lines run here, on the lines, and
    open the dialogs of the document given in the context (om_quick_add_id)."""
    _name = 'om.quick.add.line.mixin'
    _description = 'Quick Add Products: Lines'

    # the model of the document of the lines
    _om_qa_document_model = False

    def _om_qa_document_from_context(self):
        document = self.env[self._om_qa_document_model].browse(self.env.context.get('om_quick_add_id'))
        if not document.exists():
            raise UserError(_("Save the document first."))
        return document.with_context(clean_context(self.env.context))

    def om_action_quick_paste(self):
        return self._om_qa_document_from_context().om_action_quick_paste()

    def om_action_quick_history(self):
        return self._om_qa_document_from_context().om_action_quick_history()

    def om_action_quick_copy(self):
        return self._om_qa_document_from_context().om_action_quick_copy()
