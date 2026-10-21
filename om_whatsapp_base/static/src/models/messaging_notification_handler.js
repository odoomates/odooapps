/** @odoo-module **/

import { registerInstancePatchModel } from "@mail/model/model_core";

/**
 * Runs the action of the WhatsApp provider for a message written in Discuss,
 * which runs no action itself: the browser sends it, with WhatsApp Web. Only
 * the main tab of the browser runs it.
 */
registerInstancePatchModel("mail.messaging_notification_handler", "om_whatsapp_base", {
    _handleNotification(message) {
        if (message.type === "om_whatsapp/action") {
            const busService = this.env.services.bus_service;
            if (!busService || !busService.isMasterTab || busService.isMasterTab()) {
                this.env.bus.trigger("do-action", { action: message.payload.action });
            }
            return;
        }
        return this._super(...arguments);
    },
});
