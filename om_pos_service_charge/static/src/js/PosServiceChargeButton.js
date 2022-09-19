odoo.define("pos_order_to_purchase_order.PosServiceChargeButton", function (require) {
    "use strict";

    const PosComponent = require("point_of_sale.PosComponent");
    const ProductScreen = require("point_of_sale.ProductScreen");
    const {useListener} = require("web.custom_hooks");
    const Registries = require("point_of_sale.Registries");
    const {_t} = require("web.core");

    class PosServiceChargeButton extends PosComponent {
        constructor() {
            super(...arguments);
            useListener("click", this.onClick);
        }
        async onClick() {
            var self = this;
            var service_amount_type = this.env.pos.config.service_charge_type;
            var order = this.env.pos.get_order();
            var lines = order.get_orderlines();
            var product  = this.env.pos.db.get_product_by_id(this.env.pos.config.service_product_id[0]);
            if (!lines.length) {
                return this.showPopup("ErrorPopup", {
                    title: _t("Empty Order"),
                    body: _t("You need add some products"),
                });
            }
            if (product === undefined) {
                return this.showPopup("ErrorPopup", {
                    title: _t("No service product found"),
                    body: _t("The service product seems misconfigured. Make sure it is flagged as 'Can be Sold' and 'Available in Point of Sale'."),
                });
            }
            var i = 0;
            while ( i < lines.length ) {
                if (lines[i].get_product() === product) {
                     order.remove_orderline(lines[i]);
                } else {
                    i++;
                }
            }

            if (service_amount_type == 'amount'){
                const {confirmed, payload} = await this.showPopup("NumberPopup", {
                    title: this.env._t("Service Charge"),
                    startingValue: this.env.pos.config.service_charge,
                });
                if (confirmed){
                   if (payload > 0){
                       order.add_product(product, { price: payload });
                   }
                }
            }
            if (service_amount_type == 'percentage'){
                const {confirmed, payload} = await this.showPopup("NumberPopup", {
                    title: this.env._t("Service Charge %"),
                    startingValue: this.env.pos.config.service_charge,
                });
                if (confirmed){
                   var service_charge =  payload / 100.0 * order.get_total_with_tax();
                   if (service_charge > 0){
                       order.add_product(product, { price: service_charge });
                   }

                }
            }
        }
    }
    PosServiceChargeButton.template = "PosServiceChargeButton";

    ProductScreen.addControlButton({
        component: PosServiceChargeButton,
        condition: function () {
            return this.env.pos.config.enable_service_charge;
        },
    });

    Registries.Component.add(PosServiceChargeButton);

    return PosServiceChargeButton;
});
