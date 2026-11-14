/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";

import { appIconSrc } from "../launcher/launcher";

/**
 * Send the apps button to the launcher instead of the app menu.
 *
 * The button is a Dropdown with nothing to patch, so navbar_patch.xml replaces it
 * and points it here. On a narrow screen an app's own menus stay in the burger
 * menu, which is left as it is.
 */
patch(NavBar.prototype, "om_theme_lite.navbar", {
    omIconSrc(app) {
        return appIconSrc(app);
    },

    omOpenLauncher() {
        this.actionService.doAction("om_theme_lite.action_app_launcher", {
            clearBreadcrumbs: true,
        });
    },
});
