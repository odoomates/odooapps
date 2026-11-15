/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { session } from "@web/session";

/**
 * A dark mode entry in the user menu, beside Preferences.
 *
 * The scheme decides which asset bundle the page needs, so choosing it saves the
 * preference and reloads rather than restyling in place. The entry offers the
 * other scheme from the one the page shows now, so with "System" chosen it follows
 * the device; choosing it picks Light or Dark explicitly, and System stays
 * available in Preferences.
 */
export function colorSchemeItem(env) {
    const orm = env.services.orm;
    const isDark = session.om_color_scheme === "dark";

    return {
        type: "item",
        id: "om_color_scheme",
        description: isDark ? env._t("Light mode") : env._t("Dark mode"),
        callback: async () => {
            await orm.write("res.users", [env.services.user.userId], {
                om_color_scheme: isDark ? "light" : "dark",
            });
            browser.location.reload();
        },
        // Preferences is 50, so this sits directly beneath it
        sequence: 51,
    };
}

registry.category("user_menuitems").add("om_color_scheme", colorSchemeItem);
