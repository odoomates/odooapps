import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";

/**
 * Send the apps button to the launcher instead of the app menu.
 *
 * The wide-screen button is a Dropdown with nothing to patch, so navbar_patch.xml
 * replaces it and points it here.
 *
 * On a narrow screen the menu button opens a sidebar, and that sidebar is the only
 * place an app's own menus are shown. It is kept: inside an app the button still
 * opens it, and only its "All Apps" button goes to the launcher. With no app open
 * there is nothing to list, so the button goes straight to the launcher.
 */
patch(NavBar.prototype, {
    omOpenLauncher() {
        this.actionService.doAction("om_theme_lite.action_app_launcher", {
            clearBreadcrumbs: true,
        });
    },

    _openAppMenuSidebar() {
        if (this.currentApp && this.currentAppSections.length) {
            return super._openAppMenuSidebar(...arguments);
        }
        this._closeAppMenuSidebar();
        this.omOpenLauncher();
    },

    onAllAppsBtnClick() {
        this._closeAppMenuSidebar();
        this.omOpenLauncher();
    },
});
