import {
    MENU_TABS,
    MessagingMenu,
} from "@mail/core/public_web/messaging_menu/messaging_menu_model";
import { fields } from "@mail/model/export";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

MENU_TABS.OM_WHATSAPP = "om_whatsapp";

/** The WhatsApp conversations of the user, in the messaging menu and in Discuss. */
patch(MessagingMenu.prototype, {
    setup() {
        super.setup(...arguments);
        this.omWhatsappTab = fields.One("MessagingMenuTab", {
            compute() {
                if (this.store.self_user?.share !== false) {
                    return;
                }
                return {
                    id: MENU_TABS.OM_WHATSAPP,
                    recordType: "discuss.channel",
                    includesChannel: (c) =>
                        c.channel_type === "om_whatsapp" && Boolean(c.self_member_id?.is_pinned || c.isLocallyPinned),
                    icon: "oi_whatsapp",
                    activeIcon: "oi_whatsapp",
                    sequence: 25,
                    label: _t("WhatsApp"),
                    hideWhenZeroCounter: false,
                    emptyState: {
                        title: _t("No WhatsApp conversation yet"),
                        subtitle: _t("The replies of your contacts to the WhatsApp messages sent from Odoo show up here."),
                    },
                    filters: [
                        {
                            id: "om_whatsapp_unread",
                            text: _t("Unread"),
                            includesChannel: (c) => c.isUnread,
                        },
                    ],
                };
            },
            eager: true,
        });
    },
});
