import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
    // only the payment methods the cashier may use
    setup() {
        super.setup(...arguments);
        const allowed = this.pos.omPaymentMethods;
        if (allowed) {
            this.payment_methods_from_config = this.payment_methods_from_config.filter((method) =>
                allowed.includes(method.id)
            );
        }
    },
});
