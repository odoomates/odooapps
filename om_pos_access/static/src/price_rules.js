import { _t } from "@web/core/l10n/translation";

/** The price of a line before anyone changed it: the one of the pricelist. */
export function omReferencePrice(line) {
    return line.product_id.product_tmpl_id.getPrice(
        line.order_id.pricelist_id,
        line.getQuantity(),
        line.getPriceExtra(),
        false,
        line.product_id
    );
}

/**
 * Why the rules of the cashier refuse this unit price and discount on the line, or false.
 * The checks of the server are the same.
 */
export function omPriceRefusal(pos, line, unitPrice, discount) {
    if (line.refunded_orderline_id || line.combo_parent_id || line.isTipLine?.()) {
        return false;
    }
    const reference = omReferencePrice(line);
    const tolerance = 0.005;
    if (pos.omIsRestricted("price") && unitPrice < reference - tolerance) {
        return _t("You are not allowed to lower prices.");
    }
    const maxCut = pos.omLimit("max_price_cut");
    if (maxCut && unitPrice < reference * (1 - maxCut / 100) - tolerance) {
        return _t("You are allowed prices at most %s% below the pricelist.", maxCut);
    }
    const cost = line.product_id.standard_price;
    if (pos.omIsRestricted("below_cost") && cost && unitPrice * (1 - discount / 100) < cost - tolerance) {
        return _t("You are not allowed to sell below cost.");
    }
    return false;
}
