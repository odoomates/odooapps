import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { patch } from "@web/core/utils/patch";

patch(ClosePosPopup.prototype, {
    // the server checks the rules of the employee closing: tell it who that is
    async closeSession() {
        const data = this.pos.data;
        const call = data.call;
        const employeeId = this.pos.omEmployeeId;
        if (employeeId) {
            data.call = function (model, method, args, kwargs = {}) {
                if (method === "close_session_from_ui") {
                    kwargs = { ...kwargs, context: { ...(kwargs.context || {}), om_pos_employee_id: employeeId } };
                }
                return call.call(this, model, method, args, kwargs);
            };
        }
        try {
            return await super.closeSession(...arguments);
        } finally {
            data.call = call;
        }
    },
});
