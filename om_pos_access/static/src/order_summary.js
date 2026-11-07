import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(OrderSummary.prototype, {
    async updateQuantityNumber(newQuantity) {
        let line = this.currentOrder.getSelectedOrderline();
        if (line?.combo_parent_id) {
            line = line.combo_parent_id;
        }
        if (line && newQuantity !== null && newQuantity < line.getQuantity()
            && this.pos.accessRight.omIsRestricted("decrease")) {
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
        if (this.pos.accessRight.omIsRestricted("price")) {
            this.numberBuffer.reset();
            this.pos.notification.add(_t("You are not allowed to change prices."), {
                type: "warning",
            });
            return;
        }
        return super.setLinePrice(...arguments);
    },
});
