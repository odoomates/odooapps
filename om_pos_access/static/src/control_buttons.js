import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { patch } from "@web/core/utils/patch";

patch(ControlButtons.prototype, {
    // only the pricelists the cashier may sell with, and no "Default Price" when some are imposed
    getPricelistList() {
        const rights = this.pos.accessRight;
        const list = super.getPricelistList(...arguments);
        if (!rights.omPricelists) {
            return list;
        }
        return list.filter((item) => item.item && rights.omPricelistAllowed(item.item));
    },
});
