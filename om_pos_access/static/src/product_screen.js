import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";

patch(ProductScreen.prototype, {
    // the keys the rules of the cashier take away
    getNumpadButtons() {
        return super.getNumpadButtons(...arguments).map((button) => {
            if (button.value === "discount" && this.pos.omIsRestricted("discount")) {
                return { ...button, disabled: true };
            }
            if (button.value === "price" && this.pos.omIsRestricted("price")) {
                return { ...button, disabled: true };
            }
            return button;
        });
    },
});
