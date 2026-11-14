/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { appIconSrc } from "../launcher/launcher";

import { Component, onWillUnmount } from "@odoo/owl";

/**
 * A column of app icons down the left side, chosen per user in My Preferences:
 * hidden, icons only, or icons with names.
 *
 * It sits beside the whole web client rather than inside it, so no Odoo layout is
 * touched: the page is padded on the left by the sidebar's width (see theme.scss).
 * Phones have no room for it and keep their own menu.
 */
export class AppsSidebar extends Component {
    static template = "om_theme_lite.AppsSidebar";
    static props = {};

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.ui = useService("ui");
        this.type = session.om_sidebar_type || "none";
        if (this.type !== "none") {
            document.body.classList.add("o_om_sidebar", `o_om_sidebar_${this.type}`);
            onWillUnmount(() =>
                document.body.classList.remove("o_om_sidebar", `o_om_sidebar_${this.type}`)
            );
        }
    }

    get visible() {
        return this.type !== "none" && !this.ui.isSmall;
    }

    get apps() {
        return this.menuService.getApps();
    }

    get currentApp() {
        return this.menuService.getCurrentApp();
    }

    href(app) {
        return `/web#menu_id=${app.id}&action=${app.actionID}`;
    }

    openHome(ev) {
        ev.preventDefault();
        this.actionService.doAction("om_theme_lite.action_app_launcher", { clearBreadcrumbs: true });
    }

    openApp(ev, app) {
        // Ctrl, Cmd, Shift and middle click open the app in a new tab, as any link
        if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        this.menuService.selectMenu(app);
    }

    iconSrc(app) {
        return appIconSrc(app);
    }

    fontIcon(app) {
        const raw = app.webIcon;
        if (!raw || app.webIconData) {
            return null;
        }
        const [icon, color, backgroundColor] =
            typeof raw === "string" ? raw.split(",") : [raw.icon, raw.color, raw.backgroundColor];
        return icon
            ? {
                  className: icon.includes(" ") ? icon : `fa ${icon}`,
                  style: `color: ${color || "#fff"}; background-color: ${backgroundColor || "var(--om-theme-primary)"};`,
              }
            : null;
    }
}

registry.category("main_components").add("om_theme_lite.AppsSidebar", {
    Component: AppsSidebar,
});
