import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
    // only the payment methods the cashier may use
    get configPaymentMethods() {
        const allowed = this.pos.accessRight.omPaymentMethods;
        const methods = super.configPaymentMethods;
        return allowed ? methods.filter((method) => allowed.includes(method.id)) : methods;
    },
});
