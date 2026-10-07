/** @odoo-module **/

import { Component } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { jsonrpc } from "@web/core/network/rpc_service";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

/**
 * Shown while an access manager previews Odoo as another user: who is
 * previewed, through which profiles, and the way out. Nothing is saved in a
 * preview; the server refuses it.
 */
export class PreviewBanner extends Component {
    static template = "om_access_manager.PreviewBanner";

    get preview() {
        return session.om_preview;
    }

    async exit() {
        const { url } = await jsonrpc("/om_access_manager/preview/stop");
        const target = new URL(url, browser.location.href);
        const here = new URL(browser.location.href);
        browser.location.href = url;
        if (target.pathname === here.pathname && target.search === here.search) {
            // Odoo 17 URLs differ by their hash only: load the page again
            browser.location.reload();
        }
    }
}

const SEEN_KEY = "om_access_preview";
// what the web client reopens on load: the screen of the session's other user
const RESTORED_KEYS = ["current_action", "current_state", "menu_id"];

/**
 * Entering or leaving a preview starts from a clean page: the web client
 * would otherwise reopen the last screen of the other user, which the one
 * now shown may not be allowed to read.
 */
registry.category("services").add("om_access_preview_start", {
    start() {
        const current = session.om_preview ? String(session.om_preview.until) : "";
        try {
            if ((browser.sessionStorage.getItem(SEEN_KEY) || "") !== current) {
                for (const key of RESTORED_KEYS) {
                    browser.sessionStorage.removeItem(key);
                }
                if (current) {
                    browser.sessionStorage.setItem(SEEN_KEY, current);
                } else {
                    browser.sessionStorage.removeItem(SEEN_KEY);
                }
            }
        } catch {
            // no session storage: nothing was stored either
        }
    },
});

if (session.om_preview) {
    registry.category("main_components").add("om_access_manager.PreviewBanner", {
        Component: PreviewBanner,
    });
}
