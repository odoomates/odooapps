import { Navbar } from "@point_of_sale/app/navbar/navbar";
import { patch } from "@web/core/utils/patch";

patch(Navbar.prototype, {
    // Cash In/Out in the menu
    get showCashMoveButton() {
        return super.showCashMoveButton && !this.pos.omIsRestricted("cash_move");
    },
});
