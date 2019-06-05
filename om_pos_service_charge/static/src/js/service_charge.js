odoo.define('pos_service_charge.service_charge', function (require) {
"use strict";

var core = require('web.core');
var screens = require('point_of_sale.screens');

var _t = core._t;

var ServiceChargeButton = screens.ActionButtonWidget.extend({
    template: 'ServiceChargeButton',
    button_click: function(){
        var self = this;
        var service_amount_type = this.pos.config.service_charge_type;
        if (service_amount_type == 'amount'){
            this.gui.show_popup('number',{
                'title': _t('Service Charge'),
                'value': this.pos.config.service_charge,
                'confirm': function(val) {
                    self.apply_service_charge(val);
                },
            });
        }
        if (service_amount_type == 'percentage'){
            this.gui.show_popup('number',{
                'title': _t('Service Charge %'),
                'value': this.pos.config.service_charge,
                'confirm': function(val) {
                    val = Math.round(Math.max(0,Math.min(100,val)));
                    self.apply_service_charge(val);
                },
            });
        }
    },
    apply_service_charge: function(pc) {
        var order    = this.pos.get_order();
        var service_amount_type = this.pos.config.service_charge_type;
        var lines    = order.get_orderlines();
        var product  = this.pos.db.get_product_by_id(this.pos.config.service_product_id[0]);
        if (product === undefined) {
            this.gui.show_popup('error', {
                title : _t("No service product found"),
                body  : _t("The service product seems misconfigured. Make sure it is flagged as 'Can be Sold' and 'Available in Point of Sale'."),
            });
            return;
        }

        // Remove existing service charge
        var i = 0;
        while ( i < lines.length ) {
            if (lines[i].get_product() === product) {
                order.remove_orderline(lines[i]);
            } else {
                i++;
            }
        }

        // Add service_charge
        if (service_amount_type == 'amount'){
            var service_charge = pc;
        }
        if (service_amount_type == 'percentage'){
            var service_charge =  pc / 100.0 * order.get_total_with_tax();
        }

        if( service_charge > 0 ){
            order.add_product(product, { price: service_charge });
        }
    },
});

screens.define_action_button({
    'name': 'service_charge',
    'widget': ServiceChargeButton,
    'condition': function(){
        return this.pos.config.enable_service_charge && this.pos.config.service_product_id;
    },
});

return {
    ServiceChargeButton: ServiceChargeButton,
}

});
