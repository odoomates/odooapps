# What a cashier may not do in the Point of Sale: the rules (a set of fields any model can carry, on a
# user here, on an employee or an access profile in the modules built on this one), and the engine telling
# the rules of whoever is the cashier. The other modules add their own sources of rules by overriding
# _om_pos_user_rules and, with employees, _om_pos_employee_rules.
from odoo import _, api, fields, models

# restriction: the field carrying it
POS_RESTRICTIONS = {
    'refund': 'om_pos_no_refund',
    'discount': 'om_pos_no_discount',
    'price': 'om_pos_no_price_change',
    'below_cost': 'om_pos_no_below_cost',
    'cash_move': 'om_pos_no_cash_move',
    'close': 'om_pos_no_close',
    'partner': 'om_pos_no_partner_edit',
    'decrease': 'om_pos_no_decrease',
    'cancel': 'om_pos_no_cancel',
    'refund_receipt': 'om_pos_refund_receipt_only',
}
# limit: the field carrying it, a percentage (an amount for the refunds), 0 for none
POS_LIMITS = {
    'max_discount': 'om_pos_max_discount',
    'max_price_cut': 'om_pos_max_price_cut',
    'max_refund': 'om_pos_max_refund',
}
# list of allowed records: the key the rules give it under, None for all
POS_LISTS = ('payment_methods', 'pricelists')


class OmPosAccessRules(models.AbstractModel):
    """ The Point of Sale rules of someone: on a user, an employee, an access profile. """
    _name = 'om.pos.access.rules'
    _description = 'Point of Sale Restrictions'

    om_pos_no_refund = fields.Boolean(
        string='No Refunds',
        help="The Refund button of the Point of Sale is hidden, and refunds sent anyway are refused.")
    om_pos_no_discount = fields.Boolean(
        string='No Discounts',
        help="The discount key (%) of the Point of Sale is disabled, and orders sent with a discounted line, or "
             "with the global discount, are refused. Refunding a discounted sale stays possible.")
    om_pos_max_discount = fields.Float(
        string='Maximum Discount (%)',
        help="The highest discount that may be given on a line. 0 for no limit.")
    om_pos_no_price_change = fields.Boolean(
        string='No Price Changes',
        help="The price key of the Point of Sale is disabled, and a price below the one of the pricelist is refused.")
    om_pos_max_price_cut = fields.Float(
        string='Maximum Price Cut (%)',
        help="How far below the price of the pricelist a price may be set. 0 for no limit.")
    om_pos_no_cash_move = fields.Boolean(
        string='No Cash In or Out',
        help="The Cash In/Out button of the Point of Sale is hidden, and cash moves sent anyway are refused.")
    om_pos_no_close = fields.Boolean(
        string='No Closing the Register',
        help="Close Register is hidden from the menu of the Point of Sale, and closing sent anyway is refused.")
    om_pos_no_partner_edit = fields.Boolean(
        string='No Creating or Editing Customers',
        help="Create and Edit are hidden from the customers of the Point of Sale, and saving a customer from it is "
             "refused. Choosing a customer stays possible.")
    om_pos_no_decrease = fields.Boolean(
        string='No Removing Lines or Lowering Quantities',
        help="Once a product is on the order, it cannot be removed nor its quantity lowered: a manager has to. "
             "Checked on the screen of the Point of Sale only: the server only sees the final order.")
    om_pos_payment_method_ids = fields.Many2many(
        'pos.payment.method', string='Only These Payment Methods',
        help="Leave empty to allow every payment method of the shop. Set, only these are shown and may be used, "
             "and orders paid otherwise are refused.")
    om_pos_no_below_cost = fields.Boolean(
        string='Never Below Cost',
        help="A price or a discount that sells a product for less than its cost is refused.")
    om_pos_no_cancel = fields.Boolean(
        string='No Cancelling Orders',
        help="Cancel Order is hidden, an order with products cannot be deleted from the list of orders, and "
             "cancelling an order sent anyway is refused.")
    om_pos_refund_receipt_only = fields.Boolean(
        string='Refunds Only From a Receipt',
        help="A refund goes through Orders, from the receipt of the sale: a line made negative with the +/- key is "
             "refused.")
    om_pos_max_refund = fields.Float(
        string='Maximum Refund',
        help="The highest amount, taxes included, an order may give back, in the currency of the shop. 0 for no "
             "limit.")
    om_pos_pricelist_ids = fields.Many2many(
        'product.pricelist', string='Only These Pricelists',
        help="Leave empty to allow every pricelist of the shop. Set, only these can be chosen, and orders with "
             "another pricelist are refused: the price and discount limits are measured against them.")

    def _om_pos_own_rules(self):
        """ The rules this record sets, as the engine reads them. """
        self.ensure_one()
        return {
            'flags': sorted(key for key, field_name in POS_RESTRICTIONS.items() if self[field_name]),
            **{key: self[field_name] or None for key, field_name in POS_LIMITS.items()},
            'payment_methods': self.om_pos_payment_method_ids.ids or None,
            'pricelists': self.om_pos_pricelist_ids.ids or None,
        }


class OmPosAccess(models.AbstractModel):
    """ The rules of the cashier of a shop, from every source the installed modules add. """
    _name = 'om.pos.access'
    _description = 'Point of Sale Access Control'

    @api.model
    def _om_pos_no_rules(self):
        return {'flags': [], **dict.fromkeys(POS_LIMITS), 'payment_methods': None, 'pricelists': None}

    @api.model
    def _om_pos_empty(self, rules):
        return not rules['flags'] and not any(rules[key] for key in POS_LIMITS) \
            and all(rules.get(key) is None for key in POS_LISTS)

    @api.model
    def _om_pos_merge(self, *rules_list):
        """ Several rules of the same cashier, from several sources: all of them apply, so the strictest
        wins. Every restriction, the lowest limit, the payment methods and pricelists all of them allow. """
        result = self._om_pos_no_rules()
        flags = set()
        for rules in rules_list:
            flags.update(rules['flags'])
            for key in POS_LIMITS:
                if rules.get(key) and (not result[key] or rules[key] < result[key]):
                    result[key] = rules[key]
            for key in POS_LISTS:
                if rules.get(key) is not None:
                    result[key] = sorted(set(rules[key]) if result[key] is None else set(result[key]) & set(rules[key]))
        result['flags'] = sorted(flags)
        return result

    @api.model
    def _om_pos_user_rules(self, user):
        """ The rules of an Odoo user: those set on the user. """
        return user.sudo()._om_pos_own_rules()

    @api.model
    def _om_pos_rules(self, user, employee=None):
        """ The rules of the cashier: om_pos_access_hr tells those of an employee. """
        return self._om_pos_user_rules(user)

    @api.model
    def _om_pos_restrictions(self, config):
        """ What the shop loads: {'users': {id: rules}}; om_pos_access_hr adds the employees. """
        result = {'users': {}}
        for user in self.env['res.users'].sudo().search([('share', '=', False)]):
            rules = self._om_pos_user_rules(user)
            if not self._om_pos_empty(rules):
                result['users'][str(user.id)] = rules
        return result

    @api.model
    def _om_pos_refuse(self, key, user, employee=None):
        return key in self._om_pos_rules(user, employee)['flags']

    @api.model
    def _om_pos_message(self, key, **values):
        messages = {
            'refund': _("You are not allowed to refund in the Point of Sale."),
            'discount': _("You are not allowed to give discounts in the Point of Sale."),
            'max_discount': _("You are allowed discounts up to %(limit)s%% in the Point of Sale."),
            'price': _("You are not allowed to lower prices in the Point of Sale."),
            'max_price_cut': _("You are allowed prices at most %(limit)s%% below the pricelist."),
            'below_cost': _("You are not allowed to sell %(product)s below its cost."),
            'cash_move': _("You are not allowed to put cash in or take it out in the Point of Sale."),
            'close': _("You are not allowed to close the register."),
            'partner': _("You are not allowed to create or edit customers in the Point of Sale."),
            'payment_method': _("You are not allowed to take payments by %(method)s."),
            'pricelist': _("You are not allowed to sell with the pricelist %(pricelist)s."),
            'cancel': _("You are not allowed to cancel orders in the Point of Sale."),
            'refund_receipt': _("Refunds are only allowed from the receipt of the sale, in Orders."),
            'max_refund': _("You are allowed refunds up to %(limit)s."),
        }
        return messages[key] % values if values else messages[key]
