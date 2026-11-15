/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { debounce } from "@web/core/utils/timing";
import { appIconSrc } from "../launcher/launcher";

const { Component } = owl;
const { onWillUnmount, useExternalListener } = owl.hooks;

/**
 * A column of app icons down the left side, chosen per user in My Preferences:
 * hidden, icons only, or icons with names.
 *
 * It sits beside the whole web client rather than inside it, so no Odoo layout is
 * touched: the page is padded on the left by the sidebar's width (see theme.scss).
 * Phones have no room for it and keep their own menu.
 */
export class AppsSidebar extends Component {
    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.ui = useService("ui");
        this.type = session.om_sidebar_type || "none";
        // the main components are never re-rendered from above, so the sidebar
        // redraws itself when the app or the screen size changes
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => this.render());
        useExternalListener(window, "resize", debounce(() => this.render(), 150));
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

    get currentAppId() {
        const app = this.menuService.getCurrentApp();
        return app ? app.id : null;
    }

    href(app) {
        return `/web#menu_id=${app.id}&action=${app.actionID}`;
    }

    isActive(app) {
        return this.currentAppId === app.id;
    }

    openHome(ev) {
        ev.preventDefault();
        this.actionService.doAction("om_theme_lite.action_app_launcher", { clearBreadcrumbs: true });
    }

    openApp(app, ev) {
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

AppsSidebar.template = "om_theme_lite.AppsSidebar";

registry.category("main_components").add("om_theme_lite.AppsSidebar", {
    Component: AppsSidebar,
});
