import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(TicketScreen.prototype, {
    get omRefundRefused() {
        return this.pos.accessRight.omIsRestricted("refund");
    },
    // deleting an order with products is cancelling it
    shouldHideDeleteButton(order) {
        return super.shouldHideDeleteButton(...arguments)
            || (order.lines.length > 0 && this.pos.accessRight.omIsRestricted("cancel"));
    },
    async onClickRefund() {
        if (this.omRefundRefused) {
            this.pos.notification.add(_t("You are not allowed to refund."), { type: "warning" });
            return;
        }
        return super.onClickRefund(...arguments);
    },
});
