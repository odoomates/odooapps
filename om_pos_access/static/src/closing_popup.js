import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";
import { patch } from "@web/core/utils/patch";

patch(ClosePosPopup.prototype, {
    // the server checks the rules of the cashier closing: tell it who that is
    async closeSession() {
        const data = this.pos.data;
        const call = data.call;
        const cashier = this.pos.config.module_pos_hr ? this.pos.accessRight.loggedCashier : null;
        data.call = function (model, method, args, kwargs = {}) {
            if (method === "close_session_from_ui" && cashier) {
                kwargs = { ...kwargs, context: { ...(kwargs.context || {}), om_pos_employee_id: cashier.id } };
            }
            return call.call(this, model, method, args, kwargs);
        };
        try {
            return await super.closeSession(...arguments);
        } finally {
            data.call = call;
        }
    },
});
