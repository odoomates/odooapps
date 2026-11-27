import {
    MENU_TABS,
    MessagingMenu,
} from "@mail/core/public_web/messaging_menu/messaging_menu_model";
import { fields } from "@mail/model/export";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

MENU_TABS.OM_SOCIAL = "om_social";

/** The conversations of the Social Inbox of the user, in the messaging menu and in Discuss. */
patch(MessagingMenu.prototype, {
    setup() {
        super.setup(...arguments);
        this.omSocialTab = fields.One("MessagingMenuTab", {
            compute() {
                if (this.store.self_user?.share !== false) {
                    return;
                }
                return {
                    id: MENU_TABS.OM_SOCIAL,
                    recordType: "discuss.channel",
                    includesChannel: (c) =>
                        c.channel_type === "om_social" && Boolean(c.self_member_id?.is_pinned || c.isLocallyPinned),
                    icon: "forum",
                    activeIcon: "forum",
                    sequence: 25,
                    label: _t("Social Inbox"),
                    hideWhenZeroCounter: false,
                    emptyState: {
                        title: _t("No conversation yet"),
                        subtitle: _t("The replies of your customers to the messages sent from Odoo show up here."),
                    },
                    filters: [
                        {
                            id: "om_social_unread",
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
