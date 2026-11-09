# The Point of Sale rules of POS Access Control, on the access profiles: every cashier of a profile gets
# them, merged with the rules set on the cashier themselves (the strictest wins).
from odoo import api, fields, models

from odoo.addons.om_pos_access.models.pos_access import POS_LIMITS, POS_RESTRICTIONS


class OmAccessProfile(models.Model):
    _name = 'om.access.profile'
    _inherit = ['om.access.profile', 'om.pos.access.rules']

    # changes kept in the history of the profile, as its other rules
    om_pos_no_refund = fields.Boolean(tracking=True)
    om_pos_no_discount = fields.Boolean(tracking=True)
    om_pos_max_discount = fields.Float(tracking=True)
    om_pos_no_price_change = fields.Boolean(tracking=True)
    om_pos_max_price_cut = fields.Float(tracking=True)
    om_pos_no_cash_move = fields.Boolean(tracking=True)
    om_pos_no_close = fields.Boolean(tracking=True)
    om_pos_no_partner_edit = fields.Boolean(tracking=True)
    om_pos_no_decrease = fields.Boolean(tracking=True)
    # the table the profiles have always used: the payment methods already set stay
    om_pos_payment_method_ids = fields.Many2many(
        relation='om_access_profile_pos_payment_method_rel', column1='profile_id', column2='method_id',
        tracking=True)
    om_pos_no_below_cost = fields.Boolean(tracking=True)
    om_pos_no_cancel = fields.Boolean(tracking=True)
    om_pos_refund_receipt_only = fields.Boolean(tracking=True)
    om_pos_max_refund = fields.Float(tracking=True)
    om_pos_pricelist_ids = fields.Many2many(
        relation='om_access_profile_pos_pricelist_rel', column1='profile_id', column2='pricelist_id', tracking=True)

    @api.model
    def _om_pos_combine(self, profiles):
        """ The POS rules of someone in these profiles, combined as the other rules of the profiles: a
        restriction of every additive profile or of any override one; the loosest limit of the additive
        profiles (none when one of them sets none), tightened by the override ones. """
        additive = profiles.filtered(lambda profile: profile.strictness == 'additive')
        override = profiles - additive
        flags = sorted(key for key, field_name in POS_RESTRICTIONS.items()
                       if any(override.mapped(field_name)) or (additive and all(additive.mapped(field_name))))
        rules = {'flags': flags}
        for key, field_name in POS_LIMITS.items():
            limits = []
            values = additive.mapped(field_name)
            if additive and all(value > 0 for value in values):
                limits.append(max(values))
            limits += [value for value in override.mapped(field_name) if value > 0]
            rules[key] = min(limits) if limits else None
        # payment methods and pricelists: any additive profile allowing them all allows them all; override ones
        # narrow
        for key, field_name in (('payment_methods', 'om_pos_payment_method_ids'),
                                ('pricelists', 'om_pos_pricelist_ids')):
            allowed = None
            if additive and all(profile[field_name] for profile in additive):
                allowed = set(additive[field_name].ids)
            for profile in override.filtered(field_name):
                allowed = set(profile[field_name].ids) if allowed is None else allowed & set(profile[field_name].ids)
            rules[key] = sorted(allowed) if allowed is not None else None
        return rules


class OmPosAccess(models.AbstractModel):
    _inherit = 'om.pos.access'

    @api.model
    def _om_pos_profile_rules(self, user):
        """ The POS rules of the access profiles that apply to an Odoo user. """
        Profile = self.env['om.access.profile']
        rules = Profile._resolve(user.id)
        if not rules.enabled:
            return self._om_pos_no_rules()
        ids = [profile.id for profile in rules.additive + rules.override]
        return Profile._om_pos_combine(Profile.sudo().browse(ids))

    @api.model
    def _om_pos_user_rules(self, user):
        return self._om_pos_merge(super()._om_pos_user_rules(user), self._om_pos_profile_rules(user))
