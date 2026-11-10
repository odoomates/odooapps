import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(OrderSummary.prototype, {
    omRefundMessage() {
        return this.pos.omIsRestricted("refund")
            ? _t("You are not allowed to refund.")
            : _t("Refunds are only allowed from the receipt of the sale, in Orders.");
    },
    omRefundRefused() {
        return this.pos.omIsRestricted("refund") || this.pos.omIsRestricted("refund_receipt");
    },
    // the +/- key gives money back without the receipt of the sale
    async updateSelectedOrderline({ buffer, key }) {
        if (key === "-" && this.omRefundRefused()) {
            this.numberBuffer.reset();
            this.pos.notification.add(this.omRefundMessage(), { type: "warning" });
            return;
        }
        return super.updateSelectedOrderline(...arguments);
    },
    async updateQuantityNumber(newQuantity) {
        let line = this.currentOrder.getSelectedOrderline();
        if (line?.combo_parent_id) {
            line = line.combo_parent_id;
        }
        // a negative quantity typed on a sale gives money back: a refund without its receipt
        if (line && newQuantity !== null && newQuantity < 0 && !line.refunded_orderline_id
            && this.omRefundRefused()) {
            this.numberBuffer.reset();
            this.pos.notification.add(this.omRefundMessage(), { type: "warning" });
            return false;
        }
        if (line && newQuantity !== null && newQuantity < line.getQuantity()
            && this.pos.omIsRestricted("decrease")) {
            this.pos.notification.add(_t("You are not allowed to remove lines or lower quantities."), {
                type: "warning",
            });
            return false;
        }
        return super.updateQuantityNumber(...arguments);
    },
    // the price key: refused only when any change is forbidden. A limit is checked at
    // payment, as the keys build the price one digit at a time
    async setLinePrice(line, price) {
        if (this.pos.omIsRestricted("price")) {
            this.numberBuffer.reset();
            this.pos.notification.add(_t("You are not allowed to change prices."), { type: "warning" });
            return;
        }
        return super.setLinePrice(...arguments);
    },
});
