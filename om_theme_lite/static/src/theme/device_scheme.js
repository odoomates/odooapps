import { browser } from "@web/core/browser/browser";
import { cookie } from "@web/core/browser/cookie";
import { session } from "@web/session";

/**
 * Report the device's light or dark setting to the server, for the "System" scheme.
 *
 * The asset bundle is chosen on the server, which cannot see the device setting,
 * so the browser writes it into a cookie on every page. It is written whatever the
 * user's choice, so switching to System takes effect on the next page without an
 * extra round trip. With System chosen, a page served the wrong way round (the very
 * first visit, or the device switching at sunset) reloads once to match.
 */
const query = browser.matchMedia?.("(prefers-color-scheme: dark)");

function sync() {
    const device = query?.matches ? "dark" : "light";
    cookie.set("om_device_scheme", device);
    if (session.om_color_scheme_pref === "system" && session.om_color_scheme !== device) {
        browser.location.reload();
    }
}

if (query) {
    sync();
    query.addEventListener?.("change", sync);
}
