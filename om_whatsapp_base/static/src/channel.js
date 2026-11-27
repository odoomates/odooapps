import { _t } from "@web/core/l10n/translation";
import { socialChannels } from "@om_social_base/channels";

/** WhatsApp in the Social Inbox: its icon, name and image. */
socialChannels.add("whatsapp", {
    icon: "oi_whatsapp",
    label: _t("WhatsApp"),
    iconSrc: "/om_whatsapp_base/static/description/icon.png",
});
