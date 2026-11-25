from odoo import fields, models


class OmSubscriptionPlan(models.Model):
    _inherit = 'om.subscription.plan'

    website_published = fields.Boolean(
        string='Published on Website', copy=False,
        help='Offer this plan on the website shop, for the subscription products that have a recurring '
             'price for it.')

    def _get_website_period_label(self):
        """Billing period for prices on the website, e.g. "month" or "3 months"."""
        self.ensure_one()
        if self.billing_period_value == 1:
            return self._unit_singular()
        labels = dict(self._fields['billing_period_unit']._description_selection(self.env))
        return self.env._('%(count)s %(unit)s', count=self.billing_period_value,
                          unit=labels.get(self.billing_period_unit, '').lower())

    def _is_website_available(self, website):
        """Whether this plan can be sold on `website`."""
        self.ensure_one()
        return self.active and self.website_published and (
            not self.company_id or self.company_id == website.company_id)
