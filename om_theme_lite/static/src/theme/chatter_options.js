import { patch } from "@web/core/utils/patch";
import { browser } from "@web/core/browser/browser";
import { Chatter } from "@mail/chatter/web_portal_project/chatter";

import { signal } from "@odoo/owl";

// The chatter's width beside the form, and whether field changes are hidden, are
// kept in the browser: they depend on the screen, not on the person.
const WIDTH_KEY = "om_theme_lite.chatter_width";
const HIDE_TRACKING_KEY = "om_theme_lite.chatter_hide_tracking";
const MIN_WIDTH = 320;
const MAX_WIDTH = 960;

function storedWidth() {
    const width = parseInt(browser.localStorage.getItem(WIDTH_KEY), 10);
    return width >= MIN_WIDTH && width <= MAX_WIDTH ? width : null;
}

function applyWidth(width) {
    const root = document.documentElement;
    if (width) {
        root.style.setProperty("--om-chatter-width", `${width}px`);
        root.classList.add("o_om_chatter_sized");
    } else {
        root.style.removeProperty("--om-chatter-width");
        root.classList.remove("o_om_chatter_sized");
    }
}

function applyHideTracking(hide) {
    document.documentElement.classList.toggle("o_om_hide_tracking", hide);
}

applyWidth(storedWidth());
applyHideTracking(browser.localStorage.getItem(HIDE_TRACKING_KEY) === "1");

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        this.omHideTracking = signal(browser.localStorage.getItem(HIDE_TRACKING_KEY) === "1");
    },

    /** Show or hide the "Old value -> New value" lines, for every record. */
    omToggleTracking() {
        const hide = !this.omHideTracking();
        this.omHideTracking.set(hide);
        browser.localStorage.setItem(HIDE_TRACKING_KEY, hide ? "1" : "0");
        applyHideTracking(hide);
    },

    /**
     * Drag the left edge of the chatter to make it wider or narrower when it sits
     * beside the form. Double-click the edge to go back to Odoo's width.
     */
    omStartResize(ev) {
        ev.preventDefault();
        const container = ev.currentTarget.closest(".o-mail-Form-chatter") || ev.currentTarget.parentElement;
        const right = container.getBoundingClientRect().right;
        const onMove = (moveEvent) => {
            const width = Math.round(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, right - moveEvent.clientX)));
            applyWidth(width);
        };
        const onUp = () => {
            browser.removeEventListener("pointermove", onMove);
            browser.removeEventListener("pointerup", onUp);
            document.body.classList.remove("o_om_chatter_resizing");
            const width = parseInt(document.documentElement.style.getPropertyValue("--om-chatter-width"), 10);
            if (width) {
                browser.localStorage.setItem(WIDTH_KEY, String(width));
            }
        };
        document.body.classList.add("o_om_chatter_resizing");
        browser.addEventListener("pointermove", onMove);
        browser.addEventListener("pointerup", onUp);
    },

    omResetWidth() {
        browser.localStorage.removeItem(WIDTH_KEY);
        applyWidth(null);
    },
});
