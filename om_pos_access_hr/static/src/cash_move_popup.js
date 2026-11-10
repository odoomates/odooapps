import { CashMovePopup } from "@point_of_sale/app/components/popups/cash_move_popup/cash_move_popup";
import { patch } from "@web/core/utils/patch";

patch(CashMovePopup.prototype, {
    // the server checks the rules of the employee moving cash: tell it who that is
    _prepareTryCashInOutPayload() {
        const payload = super._prepareTryCashInOutPayload(...arguments);
        if (this.pos.omEmployeeId) {
            payload[payload.length - 1] = { ...payload[payload.length - 1], employee_id: this.pos.omEmployeeId };
        }
        return payload;
    },
});
