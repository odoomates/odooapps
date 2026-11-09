import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { omPriceRefusal } from "./price_rules";

patch(PosStore.prototype, {
    // the Cash In/Out button of the menu and of the closing popup
    get showCashMoveButton() {
        return super.showCashMoveButton && !this.accessRight.omIsRestricted("cash_move");
    },
    // customers: the form opened from the shop tells the server who saves it
    editPartnerContext(partner) {
        const context = super.editPartnerContext(...arguments);
        context.om_pos_partner_edit = true;
        if (this.accessRight.omEmployeeId) {
            context.om_pos_employee_id = this.accessRight.omEmployeeId;
        }
        return context;
    },
    async editPartner(partner) {
        if (this.accessRight.omIsRestricted("partner")) {
            this.notification.add(_t("You are not allowed to create or edit customers."), {
                type: "warning",
            });
            return;
        }
        return super.editPartner(...arguments);
    },
    // quantities: entered in a popup, never lowered
    disallowLineQuantityChange() {
        return super.disallowLineQuantityChange(...arguments) || this.accessRight.omIsRestricted("decrease");
    },
    async closeSession() {
        if (this.accessRight.omIsRestricted("close")) {
            this.notification.add(_t("You are not allowed to close the register."), {
                type: "warning",
            });
            return;
        }
        return super.closeSession(...arguments);
    },
    async cashMove() {
        if (this.accessRight.omIsRestricted("cash_move")) {
            this.notification.add(_t("You are not allowed to put cash in or take it out."), { type: "warning" });
            return;
        }
        return super.cashMove(...arguments);
    },
    // every discount goes through here: the key, the popup, a barcode
    async setDiscountFromUI(line, value) {
        const rights = this.accessRight;
        let discount = parseFloat(value) || 0;
        if (discount > 0 && rights.omIsRestricted("discount")) {
            this.notification.add(_t("You are not allowed to give discounts."), { type: "warning" });
            return;
        }
        const max = rights.omLimit("max_discount");
        if (max && discount > max) {
            this.notification.add(_t("You are allowed discounts up to %s%.", max), {
                type: "warning",
            });
            discount = max;
        }
        return super.setDiscountFromUI(line, discount === parseFloat(value) ? value : discount);
    },
    // orders with products: deleted from Cancel Order, from the list of orders, in a restaurant
    async onDeleteOrder(order) {
        if (order?.lines?.length && this.accessRight.omIsRestricted("cancel")) {
            this.notification.add(_t("You are not allowed to cancel orders."), { type: "warning" });
            return false;
        }
        return super.onDeleteOrder(...arguments);
    },
    // the server checks the rules of the cashier cancelling: tell it who that is
    async deleteOrders() {
        const data = this.data;
        const call = data.call;
        const employeeId = this.accessRight.omEmployeeId;
        if (employeeId) {
            data.call = function (model, method, args, kwargs = {}) {
                if (method === "cancel_order_from_pos") {
                    kwargs = { ...kwargs, context: { ...(kwargs.context || {}), om_pos_employee_id: employeeId } };
                }
                return call.call(this, model, method, args, kwargs);
            };
        }
        try {
            return await super.deleteOrders(...arguments);
        } finally {
            data.call = call;
        }
    },
    // what the order gives back and its pricelist: checked before paying, as on the server
    omOrderRefusal(order) {
        const rights = this.accessRight;
        if (!rights.omPricelistAllowed(order.pricelist_id)) {
            return _t("You are not allowed to sell with the pricelist %s: choose another one.",
                order.pricelist_id.display_name);
        }
        const returned = order.getOrderlines().filter(
            (line) => line.getQuantity() < 0 && !line.combo_parent_id && !line.is_reward_line
        );
        if (!returned.length) {
            return false;
        }
        if (rights.omIsRestricted("refund")) {
            return _t("You are not allowed to refund.");
        }
        if (rights.omIsRestricted("refund_receipt") && returned.some((line) => !line.refunded_orderline_id)) {
            return _t("Refunds are only allowed from the receipt of the sale, in Orders.");
        }
        const max = rights.omLimit("max_refund");
        const refunded = returned.reduce((total, line) => total + Math.abs(line.priceIncl), 0);
        if (max && refunded > max + 0.005) {
            return _t("You are allowed refunds up to %s.", this.formatCurrency(max));
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
            const refusal = omPriceRefusal(this.accessRight, line, line.price_unit, line.getDiscount());
            if (refusal) {
                order.selectOrderline(line);
                this.notification.add(`${line.getFullProductName()}: ${refusal}`, { type: "danger" });
                return;
            }
        }
        return super.pay(...arguments);
    },
});
