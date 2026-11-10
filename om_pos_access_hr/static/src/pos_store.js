import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    get omEmployeeId() {
        const cashier = this.get_cashier();
        return this.config.module_pos_hr && cashier && cashier !== this.user ? cashier.id : null;
    },
    // customers: the server checks the rules of the employee saving them
    editPartnerContext(partner) {
        const context = super.editPartnerContext(...arguments);
        if (this.omEmployeeId) {
            context.om_pos_employee_id = this.omEmployeeId;
        }
        return context;
    },
    // the server checks the rules of the employee cancelling: tell it who that is
    async deleteOrders() {
        const data = this.data;
        const call = data.call;
        const employeeId = this.omEmployeeId;
        if (employeeId) {
            data.call = function (model, method, args, kwargs = {}) {
                if (method === "action_pos_order_cancel") {
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
});
