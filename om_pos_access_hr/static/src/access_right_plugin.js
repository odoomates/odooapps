import { PosAccessRightPlugin } from "@point_of_sale/app/plugins/access_right_plugin";
import { patch } from "@web/core/utils/patch";

patch(PosAccessRightPlugin.prototype, {
    // pos_hr decides the +/- key by the role of the employee alone: the refund rules take it away too
    get canNegateQuantity() {
        return super.canNegateQuantity && !this.omIsRestricted("refund") && !this.omIsRestricted("refund_receipt");
    },
});
