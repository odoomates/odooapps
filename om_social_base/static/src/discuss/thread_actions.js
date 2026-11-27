import { registerThreadAction } from "@mail/core/common/thread_actions";
import { _t } from "@web/core/l10n/translation";

/** The document a conversation last spoke about, from its header. */
registerThreadAction("om-social-document", {
    condition: ({ channel }) => channel?.channel_type === "om_social" && Boolean(channel.om_social_document_name),
    icon: "description",
    name: ({ channel }) => _t("Open %(document)s", { document: channel.om_social_document_name }),
    onSelected: async ({ channel, owner }) => {
        const action = await owner.env.services.orm.call(
            "discuss.channel",
            "om_social_action_open_document",
            [[channel.id]]
        );
        await owner.env.services.action.doAction(action);
    },
    sequence: 5,
    sequenceQuick: 30,
});

/** An unknown customer: make them a contact, from the form filled with their address and name. */
registerThreadAction("om-social-create-contact", {
    condition: ({ channel }) => channel?.channel_type === "om_social" && channel.om_social_has_contact === false,
    icon: "person_add",
    name: _t("Create Contact"),
    onSelected: async ({ channel, owner }) => {
        const { action, orm } = owner.env.services;
        const formAction = await orm.call("discuss.channel", "om_social_action_create_contact", [[channel.id]]);
        await action.doAction(formAction, {
            onClose: async () => {
                const [values] = await orm.read("discuss.channel", [channel.id], ["name", "om_social_partner_id"]);
                channel.name = values.name;
                channel.om_social_has_contact = Boolean(values.om_social_partner_id);
            },
        });
    },
    sequence: 4,
    sequenceQuick: 35,
});
