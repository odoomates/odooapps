import { patch } from '@web/core/utils/patch';
import { AddToCart } from '@website_sale/interactions/add_to_cart';

patch(AddToCart.prototype, {
    /**
     * Add the plan chosen on the product page, for subscription products.
     *
     * @param {HTMLElement} el
     */
    _getOptionalParams(el) {
        const params = super._getOptionalParams(...arguments);
        const input = el.querySelector(
            '.o_wsub_plans input[name="subscription_plan_id"]:checked,'
            + ' .o_wsub_plans input[name="subscription_plan_id"][type="hidden"]'
        );
        if (input) {
            params.subscription_plan_id = parseInt(input.value);
        }
        return params;
    },
});
