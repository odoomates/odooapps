odoo.define('point_of_sale.pos_orders', function(require) {
"use strict";

var screens = require('point_of_sale.screens');
var gui = require('point_of_sale.gui');
var core = require('web.core');
var rpc = require('web.rpc');
var session = require('web.session');
var models = require('point_of_sale.models');
var PopupWidget = require('point_of_sale.popups');
var ScreenWidget = screens.ScreenWidget;
var ClientListScreenWidget = screens.ClientListScreenWidget;
var Backbone = window.Backbone;
var longpolling = require('pos_longpolling');
var QWeb = core.qweb;
var _t = core._t;

var PosModelSuper = models.PosModel;

models.load_models({
    model:  'pos.order',
    fields: ['name', 'partner_id','date_order','amount_total','pos_reference','lines','state','session_id','company_id'],
    loaded: function(self, orders){
        self.orders = orders;
        }
    });

models.load_models({
    model:  'pos.order.line',
    fields: ['product_id', 'qty', 'discount','price_subtotal_incl'],
    loaded: function(self, order_lines){
        self.order_lines = order_lines;
        }
    });

var OrderPopupWidget = PopupWidget.extend({
    template: 'OrderPopupWidget',
    show: function(options){
        var self = this;
        options = options || {};
        this._super(options);
        this.order = options.order || {};
        this.line = options.line;
        this.renderElement();
    },
    click_confirm: function(){
        var self = this;
        var current_order = self.pos.get_order();
        this.line.removeClass('highlight');
        _.each(this.order.order_lines, function(l){
            var product = self.pos.db.get_product_by_id(l['product_id']);
            current_order.add_product(product,{ quantity: l['qty']});
        })
        if (this.order.partner_id){
            var partner = self.pos.db.get_partner_by_id(this.order.partner_id);
            current_order.set_client(partner);
        }
        this.gui.show_screen('products');
    },
    click_cancel: function(){
        this._super();
        this.line.removeClass('highlight');
    },
});
gui.define_popup({name:'order', widget: OrderPopupWidget});

var PosOrderScreenWidget = ScreenWidget.extend({
    template: 'PosOrderScreenWidget',
    back_screen:   'product',
    init: function(parent, options){
        var self = this;
        this._super(parent, options);
    },

    show: function(){
        var self = this;
        this._super();
        this.renderElement();
        this.$('.back').click(function(){
            self.gui.show_screen('products');
        });
        var orders = this.get_orders();
        this.render_list(orders);

        this.$('.order-list-contents').delegate('.order-line','click',function(event){
            self.line_select(event,$(this),parseInt($(this).data('id')));
        });

        var search_timeout = null;

        if(this.pos.config.iface_vkeyboard && this.chrome.widget.keyboard){
            this.chrome.widget.keyboard.connect(this.$('.searchbox input'));
        }

        this.$('.searchbox input').on('keyup',function(event){
            clearTimeout(search_timeout);
            var query = this.value;
            search_timeout = setTimeout(function(){
                self.perform_search(query,event.which === 13);
            },70);
        });

        this.$('.searchbox .search-clear').click(function(){
            self.clear_search();
        });
    },

    get_orders: function(){
        return this.gui.get_current_screen_param('orders');
    },

    render_list: function(orders){
        var contents = this.$el[0].querySelector('.order-list-contents');
        contents.innerHTML = "";
        for(var i = 0, len = Math.min(orders.length,1000); i < len; i++){
            var order   = orders[i];
            var order_line_html = QWeb.render('PosOrderLine',{widget: this, order:order});
            var order_line = document.createElement('tbody');
            order_line.innerHTML = order_line_html;
            order_line = order_line.childNodes[1];
            contents.appendChild(order_line);
        }
    },

    perform_search: function(query, associate_result){
        var orders;
        if(query){
            orders = this.search_order(query);
            this.render_list(orders);
        }else{
            orders = this.pos.orders;
            this.render_list(orders);
        }
    },
    clear_search: function(){
        var orders = this.pos.orders;
        this.render_list(orders);
        this.$('.searchbox input')[0].value = '';
        this.$('.searchbox input').focus();
    },

    search_order: function(query){
        try {
            var re = RegExp(query, 'i');
        }catch(e){
            return [];
        }
        var results = [];
        for (var order_id in this.pos.orders){
            var r = re.exec(this.pos.orders[order_id]['name']+ '|'+ this.pos.orders[order_id]['partner_id'][1]);
            if(r){
            results.push(this.pos.orders[order_id]);
            }
        }
        return results;
    },

    line_select: function(event,$line,id){
        var self = this;
        var order = this.get_order_by_id(id);
        $line.addClass('highlight');
        this.gui.show_popup('order', {
            'order': order,
            'line':$line
        })
    },
    get_order_by_id:function(id){
        var orders = this.pos.orders;
        var selected_order = [];
        var selected_lines = [];
        for (var i in orders){
            if (orders[i].id == id){
                for (var l in orders[i].lines){
                    selected_lines.push(orders[i].lines[l])
                }
                var order_lines = this.get_order_lines(selected_lines);
                selected_order.push({
                    'name': orders[i].name,
                    'partner':orders[i].partner_id[1],
                    'partner_id':orders[i].partner_id[0],
                    'session':orders[i].session_id[1],
                    'company':orders[i].company_id[1],
                    'amount_total': orders[i].amount_total,
                    'date_order': orders[i].date_order,
                    'pos_reference':orders[i].pos_reference,
                    'order_lines':order_lines,
                    'state':orders[i].state
                  })
            }
        }
        return selected_order[0];
    },

    get_order_lines:function(lines){
        var selected_lines = [];
        var order_lines = this.pos.order_lines;
        for (var l in order_lines){
            if (lines.indexOf(order_lines[l].id ) > -1){
                selected_lines.push({
                    'product': order_lines[l].product_id[1],
                    'product_id': order_lines[l].product_id[0],
                    'qty':order_lines[l].qty,
                    'discount':order_lines[l].discount,
                    'price':order_lines[l].price_subtotal_incl
                })
            }
        }
        return selected_lines;
    },
});

gui.define_screen({name:'order_list', widget: PosOrderScreenWidget});

var OrderListButton = screens.ActionButtonWidget.extend({
    template: 'OrderListButton',
    button_click: function(){
        var orders = this.pos.orders;
        this.gui.show_screen('order_list',{orders:orders});
    }
});

screens.define_action_button({
    'name': 'pos_order_list',
    'widget': OrderListButton,
});

ClientListScreenWidget = ClientListScreenWidget.include({
    init: function(parent) {
        var self = this;
        this._super(parent);
        _.extend(self.events,
            {
            "click .view_orders":"view_customer_orders",
            })
    },
    view_customer_orders:function(e){
        e.stopPropagation();
        e.preventDefault();
        var partner = $(e.target).data('id');
        var orders = this.get_customer_orders(partner);
        this.gui.show_screen('order_list',{orders:orders});
    },
    get_customer_orders:function(partner){
        var customer_orders = [];
        var orders = this.pos.orders;
        for (var i in orders){
            if(orders[i].partner_id[0]==partner){
                customer_orders.push(orders[i]);
            }
        }
        return customer_orders;
    },
});

models.PosModel = models.PosModel.extend({
    initialize: function(){
        PosModelSuper.prototype.initialize.apply(this, arguments);
        this.bus.add_channel_callback("pos_order_sync", this.on_order_create, this);
    },
    on_order_create: function(data){
        var self = this;
        var order_screen = self.gui.screen_instances.order_list;
        var fields = _.find(this.models,function(model){ return model.model === 'pos.order'; }).fields;
        var line_fields = _.find(this.models,function(model){ return model.model === 'pos.order.line'; }).fields;
        rpc.query({
            model: 'pos.order',
            method: 'search_read',
            args: [[['id', '=', data['order_id']]], fields],
            limit: 1,
        }).then(function (order){
            self.orders.unshift(order[0]);
            _.each(data['lines'], function(line_id){
                rpc.query({
                    model: 'pos.order.line',
                    method: 'search_read',
                    args: [[['id', '=', line_id]], line_fields],
                    limit: 1,
                }).then(function(line){
                    self.order_lines.push(line[0]);
                });
            });
        });

    },

});

});

