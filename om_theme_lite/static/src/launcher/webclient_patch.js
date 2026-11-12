import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";

import { clearCurrentApp } from "./launcher";

/**
 * Keep the navbar empty when the page boots on the launcher.
 *
 * On boot the webclient restores the app last opened in this tab from session
 * storage, and it does so after the home action has mounted. Opening /odoo straight
 * from Sales therefore drew the launcher with the Sales menus in the navbar. Clearing
 * once the route is fully loaded undoes that, for boot and for back and forward.
 */
patch(WebClient.prototype, {
    async loadRouterState() {
        await super.loadRouterState(...arguments);
        if (this.actionService.currentController?.action?.tag === "om_theme_lite.launcher") {
            clearCurrentApp(this.menuService);
        }
    },
});
