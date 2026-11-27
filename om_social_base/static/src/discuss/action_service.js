import { registry } from "@web/core/registry";

/**
 * Runs the action of the provider for a message written in Discuss, which
 * runs no action itself: a browser provider sends it from there. Only one tab
 * of the browser runs it.
 */
export const socialActionService = {
    dependencies: ["action", "bus_service", "multi_tab"],
    start(env, { action, bus_service, multi_tab }) {
        bus_service.subscribe("om_social/action", async ({ action: todo }) => {
            if (await multi_tab.isOnMainTab()) {
                await action.doAction(todo);
            }
        });
    },
};

registry.category("services").add("om_social_action", socialActionService);
