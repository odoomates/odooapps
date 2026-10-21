/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";
import { attr } from "@mail/model/model_field";

/** A WhatsApp conversation: what the server tells of it, and its actions. */
registerPatch({
    name: "Channel",
    recordMethods: {
        /** The document the conversation last spoke about. */
        async omWhatsappOpenDocument() {
            const action = await this.env.services.orm.call("mail.channel", "om_whatsapp_action_open_document", [[this.id]]);
            await this.env.services.action.doAction(action);
        },
        /** An unknown number: make it a contact, from the form filled with its number and WhatsApp name. */
        async omWhatsappCreateContact() {
            const { action, orm } = this.env.services;
            const formAction = await orm.call("mail.channel", "om_whatsapp_action_create_contact", [[this.id]]);
            await action.doAction(formAction, {
                onClose: async () => {
                    const [values] = await orm.read("mail.channel", [this.id], ["name", "om_whatsapp_partner_id"]);
                    if (!this.exists()) {
                        return;
                    }
                    this.update({ om_whatsapp_has_contact: Boolean(values.om_whatsapp_partner_id) });
                    if (this.thread) {
                        this.thread.update({ name: values.name });
                    }
                },
            });
        },
    },
    fields: {
        discussSidebarCategory: {
            compute() {
                if (this.channel_type === "om_whatsapp") {
                    return this.messaging.discuss.categoryOmWhatsapp;
                }
                return this._super();
            },
        },
        om_whatsapp_document_name: attr(),
        om_whatsapp_free_text_until: attr(),
        om_whatsapp_has_contact: attr(),
        om_whatsapp_number: attr(),
        om_whatsapp_provider: attr(),
        /** The photo of the contact, else the picture WhatsApp gave the number. */
        omWhatsappAvatarUrl: attr({
            compute() {
                return `/web/image/mail.channel/${this.id}/avatar_128?unique=${this.avatarCacheKey}`;
            },
        }),
    },
});
