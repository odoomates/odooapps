import { PartnerLine } from "@point_of_sale/app/screens/partner_list/partner_line/partner_line";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { patch } from "@web/core/utils/patch";

patch(PartnerLine.prototype, {
    // the rules of the cashier hide Edit Details
    setup() {
        super.setup(...arguments);
        this.pos = usePos();
    },
});
