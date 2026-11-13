import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { omPriceRefusal } from "./price_rules";

const NO_RULES = {
    flags: [],
    max_discount: null,
    max_price_cut: null,
    max_refund: null,
    payment_methods: null,
    pricelists: null,
};

patch(PosStore.prototype, {
    /**
     * The POS rules of the cashier logged in the shop: those of the employee when they have rules of
     * their own (om_pos_access_hr), else those of the employee's Odoo user, else those of the Odoo
     * user who opened the shop, as on the server.
     */
    get omRules() {
        const loaded = this.config._om_pos_restrictions || {};
        const users = loaded.users || {};
        const cashier = this.getCashier();
        if (cashier && this.config.module_pos_hr && cashier !== this.user) {
            const employees = loaded.employees || {};
            if (employees[cashier.id]) {
                return employees[cashier.id];
            }
            const userId = cashier.user_id?.id ?? cashier.user_id;
            if (userId) {
                return users[userId] || NO_RULES;
            }
        }
        return users[this.user?.id] || NO_RULES;
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
    // the ids of the pricelists allowed, or null for all of them
    get omPricelists() {
        return this.omRules.pricelists ?? null;
    },
    omPricelistAllowed(pricelist) {
        const allowed = this.omPricelists;
        return !allowed || !pricelist || allowed.includes(pricelist.id);
    },
    // the Cash In/Out button of the menu and of the closing popup
    get showCashMoveButton() {
        return super.showCashMoveButton && !this.omIsRestricted("cash_move");
    },
    cashMove() {
        if (this.omIsRestricted("cash_move")) {
            this.notification.add(_t("You are not allowed to put cash in or take it out."), { type: "warning" });
            return;
        }
        return super.cashMove(...arguments);
    },
    async closeSession() {
        if (this.omIsRestricted("close")) {
            this.notification.add(_t("You are not allowed to close the register."), { type: "warning" });
            return;
        }
        return super.closeSession(...arguments);
    },
    // customers: the form opened from the shop tells the server who saves it
    editPartnerContext(partner) {
        return { ...super.editPartnerContext(...arguments), om_pos_partner_edit: true };
    },
    async editPartner(partner) {
        if (this.omIsRestricted("partner")) {
            this.notification.add(_t("You are not allowed to create or edit customers."), { type: "warning" });
            return;
        }
        return super.editPartner(...arguments);
    },
    // quantities: entered in a popup, never lowered
    disallowLineQuantityChange() {
        return super.disallowLineQuantityChange(...arguments) || this.omIsRestricted("decrease");
    },
    // every discount goes through here: the key, the popup, a barcode
    async setDiscountFromUI(line, value) {
        let discount = parseFloat(value) || 0;
        if (discount > 0 && this.omIsRestricted("discount")) {
            this.notification.add(_t("You are not allowed to give discounts."), { type: "warning" });
            return;
        }
        const max = this.omLimit("max_discount");
        if (max && discount > max) {
            this.notification.add(_t("You are allowed discounts up to %s%.", max), { type: "warning" });
            discount = max;
        }
        return super.setDiscountFromUI(line, discount === parseFloat(value) ? value : discount);
    },
    // orders with products: deleted from Cancel Order, from the list of orders, in a restaurant
    async onDeleteOrder(order) {
        if (order?.lines?.length && this.omIsRestricted("cancel")) {
            this.notification.add(_t("You are not allowed to cancel orders."), { type: "warning" });
            return false;
        }
        return super.onDeleteOrder(...arguments);
    },
    // what the order gives back and its pricelist: checked before paying, as on the server
    omOrderRefusal(order) {
        if (!this.omPricelistAllowed(order.pricelist_id)) {
            return _t(
                "You are not allowed to sell with the pricelist %s: choose another one.",
                order.pricelist_id.display_name
            );
        }
        const returned = order
            .getOrderlines()
            .filter((line) => line.getQuantity() < 0 && !line.combo_parent_id && !line.is_reward_line);
        if (!returned.length) {
            return false;
        }
        if (this.omIsRestricted("refund")) {
            return _t("You are not allowed to refund.");
        }
        if (this.omIsRestricted("refund_receipt") && returned.some((line) => !line.refunded_orderline_id)) {
            return _t("Refunds are only allowed from the receipt of the sale, in Orders.");
        }
        const max = this.omLimit("max_refund");
        const refunded = returned.reduce((total, line) => total + Math.abs(line.priceIncl), 0);
        if (max && refunded > max + 0.005) {
            return _t("You are allowed refunds up to %s.", this.env.utils.formatCurrency(max));
        }
        return false;
    },
    // the prices and discounts of the order, once typed: checked before paying, as on the server
    async pay() {
        const order = this.getOrder();
        const refusal = order && this.omOrderRefusal(order);
        if (refusal) {
            this.notification.add(refusal, { type: "danger" });
            return;
        }
        for (const line of order?.getOrderlines() || []) {
            const refusal = omPriceRefusal(this, line, line.price_unit, line.getDiscount());
            if (refusal) {
                order.selectOrderline(line);
                this.notification.add(`${line.getFullProductName()}: ${refusal}`, { type: "danger" });
                return;
            }
        }
        return super.pay(...arguments);
    },
});
