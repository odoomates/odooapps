import { patch } from '@web/core/utils/patch';
import { patchDynamicContent } from '@web/public/utils';
import { ProductPage } from '@website_sale/interactions/product_page';

const PLAN_INPUT = '.o_wsub_plans input[name="subscription_plan_id"]';

patch(ProductPage.prototype, {
    setup() {
        super.setup();
        patchDynamicContent(this.dynamicContent, {
            [PLAN_INPUT]: { 't-on-change': this.onChangeSubscriptionPlan.bind(this) },
        });
    },

    /**
     * Highlight the chosen plan and reload the prices of the product for it.
     *
     * @param {Event} ev
     */
    onChangeSubscriptionPlan(ev) {
        const parent = ev.currentTarget.closest('.js_product');
        this._highlightSubscriptionPlan(parent);
        this._triggerVariantChange(parent);
    },

    _highlightSubscriptionPlan(parent) {
        parent.querySelectorAll('.o_wsub_plan').forEach((label) => {
            const checked = label.querySelector('input').checked;
            label.classList.toggle('active', checked);
            label.classList.toggle('border-primary', checked);
            label.classList.toggle('bg-primary-subtle', checked);
            label.classList.toggle('text-primary-emphasis', checked);
        });
    },

    /**
     * Send the chosen plan with the combination, to get its recurring price.
     *
     * @param {Element} product
     */
    _getOptionalCombinationInfoParams(product) {
        const params = super._getOptionalCombinationInfoParams(...arguments);
        const input = product.querySelector(
            `${PLAN_INPUT}:checked, ${PLAN_INPUT}[type="hidden"]`
        );
        if (input) {
            params.subscription_plan_id = parseInt(input.value);
        }
        return params;
    },

    /**
     * Update the period next to the price and the price of each plan for the selected variant.
     */
    async _onChangeCombination(ev, parent, combination) {
        await super._onChangeCombination(...arguments);
        const period = parent.querySelector('.o_wsub_period');
        if (period) {
            period.classList.toggle('d-none', !combination.subscription_period);
            period.querySelector('.o_wsub_period_label').textContent =
                combination.subscription_period || '';
        }
        const plans = combination.subscription_plans;
        if (!plans) {
            return;
        }
        const planById = Object.fromEntries(plans.map((plan) => [plan.id, plan]));
        parent.querySelectorAll('.o_wsub_plan').forEach((label) => {
            const plan = planById[parseInt(label.dataset.planId)];
            label.classList.toggle('d-none', !plan);
            if (!plan) {
                return;
            }
            const price = label.querySelector('.o_wsub_plan_price .oe_currency_value');
            if (price) {
                price.textContent = this._priceToStr(plan.price, combination.currency_precision);
            }
            label.querySelector('input').checked = plan.id === combination.subscription_plan_id;
        });
        this._highlightSubscriptionPlan(parent);
    },
});
