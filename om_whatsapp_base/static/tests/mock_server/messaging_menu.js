import { messagingMenuHelpers } from "@mail/../tests/mock_server/controllers/discuss/messaging_menu";
import { patch } from "@web/core/utils/patch";

// Mirrors om_whatsapp/controllers/messaging_menu.py: the WhatsApp tab.
patch(messagingMenuHelpers, {
    _get_menu_tab_domain(env, tab_id) {
        if (tab_id === "om_whatsapp") {
            return [
                ["channel_type", "=", "om_whatsapp"],
                ["self_member_id.is_pinned", "=", true],
            ];
        }
        return super._get_menu_tab_domain(env, tab_id);
    },
    _get_menu_tab_filter_domain(env, tab_id, filter_id) {
        if (tab_id === "om_whatsapp" && filter_id === "om_whatsapp_unread") {
            return [["self_member_id.is_unread", "=", true]];
        }
        return super._get_menu_tab_filter_domain(env, tab_id, filter_id);
    },
});
