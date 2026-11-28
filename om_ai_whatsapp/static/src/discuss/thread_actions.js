import { registerThreadAction } from "@mail/core/common/thread_actions";
import { _t } from "@web/core/l10n/translation";

async function switchAssistant(channel, owner, method, message) {
    const { orm, notification } = owner.env.services;
    channel.om_ai_whatsapp_state = await orm.call("discuss.channel", method, [[channel.id]]);
    notification.add(message, { type: "info" });
}

/** A person answers this WhatsApp customer: the AI assistant stops. */
registerThreadAction("om-ai-whatsapp-take-over", {
    condition: ({ channel }) =>
        channel?.channel_type === "om_social" && channel.om_ai_whatsapp_state === "ai",
    icon: "back_hand",
    name: _t("Take Over from the AI Assistant"),
    onSelected: ({ channel, owner }) =>
        switchAssistant(
            channel,
            owner,
            "om_ai_whatsapp_action_take_over",
            _t("You answer this customer now: the assistant stopped.")
        ),
    sequence: 6,
    sequenceQuick: 25,
});

/** The AI assistant answers this WhatsApp customer again. */
registerThreadAction("om-ai-whatsapp-give-back", {
    condition: ({ channel }) =>
        channel?.channel_type === "om_social" && channel.om_ai_whatsapp_state === "human",
    icon: "undo",
    name: _t("Give Back to the AI Assistant"),
    onSelected: ({ channel, owner }) =>
        switchAssistant(
            channel,
            owner,
            "om_ai_whatsapp_action_give_back",
            _t("The assistant answers this customer again.")
        ),
    sequence: 6,
    sequenceQuick: 25,
});
