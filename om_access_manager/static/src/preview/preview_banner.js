import { Component } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network/rpc";
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
        const { url } = await rpc("/om_access_manager/preview/stop");
        browser.location.href = url;
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
