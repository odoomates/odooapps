/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Runs the action of the WhatsApp provider for a message written in Discuss,
 * which runs no action itself: the browser sends it, with WhatsApp Web. Only
 * one tab of the browser runs it.
 */
export const whatsappActionService = {
    dependencies: ["action", "bus_service", "multi_tab"],
    start(env, { action, bus_service, multi_tab }) {
        bus_service.addEventListener("notification", ({ detail: notifications }) => {
            for (const { payload, type } of notifications) {
                if (type === "om_whatsapp/action" && multi_tab.isOnMainTab()) {
                    action.doAction(payload.action);
                }
            }
        });
    },
};

registry.category("services").add("om_whatsapp_action", whatsappActionService);
