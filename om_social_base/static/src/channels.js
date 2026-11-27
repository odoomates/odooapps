import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

/**
 * The messaging channels of the Social Inbox: channel modules add theirs to
 * the registry ``om_social_channels``, by the key of the channel of their
 * accounts, with the icon, the name and the image shown for it.
 */
export const socialChannels = registry.category("om_social_channels");

export function getSocialChannel(code) {
    return socialChannels.get(code, {
        icon: "forum",
        label: _t("Social Inbox"),
        iconSrc: "/om_social_base/static/description/icon.png",
    });
}
