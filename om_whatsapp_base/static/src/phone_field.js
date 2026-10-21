/** @odoo-module **/

import basicFields from "web.basic_fields";
import session from "web.session";
import { WHATSAPP_GROUP, whatsappComposerAction } from "./whatsapp_composer";

/** The WhatsApp button next to a phone number: the composer, to that number. */
basicFields.FieldPhone.include({
    events: Object.assign({}, basicFields.FieldPhone.prototype.events, {
        "click .o_om_whatsapp_phone": "_onClickOmWhatsapp",
    }),

    willStart() {
        return Promise.all([
            this._super(...arguments),
            session.user_has_group(WHATSAPP_GROUP).then((allowed) => (this.canOmWhatsapp = allowed)),
        ]);
    },

    _renderReadonly() {
        this._super(...arguments);
        if (this.value && this.canOmWhatsapp && this.res_id) {
            const button = $("<a>", {
                href: "#",
                class: "o_om_whatsapp_phone ml-3 d-inline-flex align-items-center",
                title: this._t ? this._t("Send a WhatsApp message") : "Send a WhatsApp message",
            }).append($("<i>", { class: "fa fa-whatsapp" }), $("<small>", { class: "font-weight-bold ml-1", text: "WhatsApp" }));
            this.$el.append(button);
        }
    },

    _onClickOmWhatsapp(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.do_action(whatsappComposerAction({ resModel: this.model, resIds: [this.res_id], number: this.value }), {
            on_close: () => this.trigger_up("reload"),
        });
    },
});
