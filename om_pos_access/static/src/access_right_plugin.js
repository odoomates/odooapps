import { PosAccessRightPlugin } from "@point_of_sale/app/plugins/access_right_plugin";
import { patch } from "@web/core/utils/patch";

const NO_RULES = {
    flags: [],
    max_discount: null,
    max_price_cut: null,
    max_refund: null,
    payment_methods: null,
    pricelists: null,
};

patch(PosAccessRightPlugin.prototype, {
    /**
     * The POS rules of the cashier logged in the shop: those of the employee when they have rules of
     * their own (om_pos_access_hr), else those of the employee's Odoo user, else those of the Odoo
     * user who opened the shop, as on the server.
     */
    get omRules() {
        const loaded = this.config._om_pos_restrictions || {};
        const users = loaded.users || {};
        const cashier = this.loggedCashier;
        if (cashier && this.config.module_pos_hr) {
            const employees = loaded.employees || {};
            if (employees[cashier.id]) {
                return employees[cashier.id];
            }
            const userId = cashier.user_id?.id ?? cashier.user_id;
            if (userId) {
                return users[userId] || NO_RULES;
            }
        }
        const shopUser = this.data.models["res.users"].getFirst();
        return users[shopUser?.id] || NO_RULES;
    },
    omIsRestricted(key) {
        return this.omRules.flags.includes(key);
    },
    omLimit(key) {
        return this.omRules[key] || 0;
    },
    // the ids of the payment methods allowed, or null for all of them
    get omPaymentMethods() {
        return this.omRules.payment_methods ?? null;
    },
    // the +/- key: a negative quantity or price gives money back without the receipt of the sale
    get canNegateQuantity() {
        return super.canNegateQuantity && !this.omIsRestricted("refund") && !this.omIsRestricted("refund_receipt");
    },
    // the ids of the pricelists allowed, or null for all of them
    get omPricelists() {
        return this.omRules.pricelists ?? null;
    },
    omPricelistAllowed(pricelist) {
        const allowed = this.omPricelists;
        return !allowed || !pricelist || allowed.includes(pricelist.id);
    },
    get omEmployeeId() {
        return this.config.module_pos_hr ? this.loggedCashier?.id : null;
    },
});
