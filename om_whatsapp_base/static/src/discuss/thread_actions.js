import { registerThreadAction } from "@mail/core/common/thread_actions";
import { _t } from "@web/core/l10n/translation";

/** The document a WhatsApp conversation last spoke about, from its header. */
registerThreadAction("om-whatsapp-document", {
    condition: ({ channel }) => channel?.channel_type === "om_whatsapp" && Boolean(channel.om_whatsapp_document_name),
    icon: "description",
    name: ({ channel }) => _t("Open %(document)s", { document: channel.om_whatsapp_document_name }),
    onSelected: async ({ channel, owner }) => {
        const action = await owner.env.services.orm.call(
            "discuss.channel",
            "om_whatsapp_action_open_document",
            [[channel.id]]
        );
        await owner.env.services.action.doAction(action);
    },
    sequence: 5,
    sequenceQuick: 30,
});

/** An unknown number: make it a contact, from the form filled with its number and WhatsApp name. */
registerThreadAction("om-whatsapp-create-contact", {
    condition: ({ channel }) => channel?.channel_type === "om_whatsapp" && channel.om_whatsapp_has_contact === false,
    icon: "person_add",
    name: _t("Create Contact"),
    onSelected: async ({ channel, owner }) => {
        const { action, orm } = owner.env.services;
        const formAction = await orm.call("discuss.channel", "om_whatsapp_action_create_contact", [[channel.id]]);
        await action.doAction(formAction, {
            onClose: async () => {
                const [values] = await orm.read("discuss.channel", [channel.id], ["name", "om_whatsapp_partner_id"]);
                channel.name = values.name;
                channel.om_whatsapp_has_contact = Boolean(values.om_whatsapp_partner_id);
            },
        });
    },
    sequence: 4,
    sequenceQuick: 35,
});
