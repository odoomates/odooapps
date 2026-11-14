/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { browser } from "@web/core/browser/browser";
import { session } from "@web/session";
import { FormController } from "@web/views/form/form_controller";
import { FormRenderer } from "@web/views/form/form_renderer";
import { Chatter } from "@mail/components/chatter/chatter";
import { ChatterTopbar } from "@mail/components/chatter_topbar/chatter_topbar";
import { SIZES } from "@web/core/ui/ui_service";

import { useState } from "@odoo/owl";

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

/**
 * "Below the form": the chatter stays underneath even on a wide screen.
 *
 * Odoo puts the chatter (or an attachment preview) beside the sheet once the
 * screen is extra wide, and both the form controller and the form renderer decide
 * that from the screen size they read off the ui service. For this user they are
 * handed a screen size capped just under that, so a wide screen is laid out the way
 * Odoo lays out a normal one: chatter below, no preview beside it, and the
 * wide-screen class dropped.
 */
const chatterBelow = () => session.om_chatter_position === "bottom";

document.documentElement.classList.toggle("o_om_chatter_below", chatterBelow());

function capSize(ui) {
    return new Proxy(ui, {
        // read through the service itself, so a resize still re-renders
        get: (target, key) => (key === "size" ? Math.min(target.size, SIZES.XL) : target[key]),
    });
}

patch(FormRenderer.prototype, "om_theme_lite.chatter_below", {
    setup() {
        this._super(...arguments);
        if (chatterBelow() && this.uiService) {
            this.uiService = capSize(this.uiService);
        }
    },
});

patch(FormController.prototype, "om_theme_lite.chatter_below", {
    setup() {
        this._super(...arguments);
        if (chatterBelow()) {
            if (this.uiService) {
                this.uiService = capSize(this.uiService);
            }
            this.ui = capSize(this.ui);
        }
    },
});

patch(ChatterTopbar.prototype, "om_theme_lite.chatter_tracking", {
    setup() {
        this._super(...arguments);
        this.omState = useState({ hideTracking: browser.localStorage.getItem(HIDE_TRACKING_KEY) === "1" });
    },

    /** Show or hide the "Old value -> New value" lines, for every record. */
    omToggleTracking() {
        const hide = !this.omState.hideTracking;
        this.omState.hideTracking = hide;
        browser.localStorage.setItem(HIDE_TRACKING_KEY, hide ? "1" : "0");
        applyHideTracking(hide);
    },
});

patch(Chatter.prototype, "om_theme_lite.chatter_width", {
    /**
     * Drag the left edge of the chatter to make it wider or narrower when it sits
     * beside the form. Double-click the edge to go back to Odoo's width.
     */
    omStartResize(ev) {
        ev.preventDefault();
        const container = ev.currentTarget.closest(".o_FormRenderer_chatterContainer") || ev.currentTarget.parentElement;
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
