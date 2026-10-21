/** @odoo-module **/

import { registerClassPatchModel, registerFieldPatchModel, registerInstancePatchModel } from "@mail/model/model_core";
import { attr } from "@mail/model/model_field";

const OM_WHATSAPP_FIELDS = [
    "om_whatsapp_document_name",
    "om_whatsapp_free_text_until",
    "om_whatsapp_has_contact",
    "om_whatsapp_number",
    "om_whatsapp_provider",
];

registerClassPatchModel("mail.thread", "om_whatsapp_base", {
    convertData(data) {
        const data2 = this._super(data);
        for (const name of OM_WHATSAPP_FIELDS) {
            if (name in data) {
                data2[name] = data[name];
            }
        }
        return data2;
    },
});

registerFieldPatchModel("mail.thread", "om_whatsapp_base", {
    om_whatsapp_document_name: attr(),
    om_whatsapp_free_text_until: attr(),
    om_whatsapp_has_contact: attr(),
    om_whatsapp_number: attr(),
    om_whatsapp_provider: attr(),
});

/** A WhatsApp conversation: its category in Discuss, and its actions. */
registerInstancePatchModel("mail.thread", "om_whatsapp_base", {
    /** The document the conversation last spoke about. */
    async omWhatsappOpenDocument() {
        const action = await this.env.services.rpc({
            model: "mail.channel",
            method: "om_whatsapp_action_open_document",
            args: [[this.id]],
        });
        this.env.bus.trigger("do-action", { action });
    },
    /** An unknown number: make it a contact, from the form filled with its number and WhatsApp name. */
    async omWhatsappCreateContact() {
        const action = await this.env.services.rpc({
            model: "mail.channel",
            method: "om_whatsapp_action_create_contact",
            args: [[this.id]],
        });
        this.env.bus.trigger("do-action", {
            action,
            options: {
                on_close: async () => {
                    const [values] = await this.env.services.rpc({
                        model: "mail.channel",
                        method: "read",
                        args: [[this.id], ["name", "om_whatsapp_partner_id"]],
                    });
                    if (this.exists()) {
                        this.update({ name: values.name, om_whatsapp_has_contact: Boolean(values.om_whatsapp_partner_id) });
                    }
                },
            },
        });
    },
    _getDiscussSidebarCategory() {
        if (this.channel_type === "om_whatsapp") {
            return this.messaging.discuss.categoryOmWhatsapp;
        }
        return this._super();
    },
});
