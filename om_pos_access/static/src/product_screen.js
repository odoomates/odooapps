import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";

patch(ProductScreen.prototype, {
    // the keys the rules of the cashier take away
    getNumpadButtons() {
        const rights = this.pos.accessRight;
        return super.getNumpadButtons(...arguments).map((button) => {
            if (button.value === "discount" && rights.omIsRestricted("discount")) {
                return { ...button, disabled: true };
            }
            if (button.value === "price" && rights.omIsRestricted("price")) {
                return { ...button, disabled: true };
            }
            return button;
        });
    },
});
