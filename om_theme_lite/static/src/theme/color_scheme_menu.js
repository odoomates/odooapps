import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { session } from "@web/session";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";

/**
 * A dark mode switch in the user menu, beside My Preferences.
 *
 * The scheme decides which asset bundle the page needs, so flipping it saves the
 * preference and reloads rather than restyling in place. The switch shows what the
 * page looks like now, so with "System" chosen it reflects the device; flipping it
 * picks Light or Dark explicitly, and System stays available in My Preferences.
 */
export function colorSchemeItem() {
    const orm = useService("orm");
    const isDark = session.om_color_scheme === "dark";

    return {
        type: "switch",
        id: "om_color_scheme",
        description: _t("Dark mode"),
        isChecked: isDark,
        callback: async () => {
            await orm.write("res.users", [user.userId], {
                om_color_scheme: isDark ? "light" : "dark",
            });
            browser.location.reload();
        },
        // My Preferences is 50, so this sits directly beneath it
        sequence: 51,
    };
}

registry.category("user_menuitems").add("om_color_scheme", colorSchemeItem);
