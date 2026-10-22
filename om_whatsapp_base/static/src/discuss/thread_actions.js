import { registerThreadAction } from "@mail/core/common/thread_actions";
import { _t } from "@web/core/l10n/translation";

/** The document a WhatsApp conversation last spoke about, from its header. */
registerThreadAction("om-whatsapp-document", {
    condition: ({ thread }) => thread?.channel_type === "om_whatsapp" && Boolean(thread.om_whatsapp_document_name),
    icon: "fa fa-fw fa-file-text-o",
    name: ({ thread }) => _t("Open %(document)s", { document: thread.om_whatsapp_document_name }),
    open: async ({ thread, owner }) => {
        const action = await owner.env.services.orm.call(
            "discuss.channel",
            "om_whatsapp_action_open_document",
            [[thread.id]]
        );
        await owner.env.services.action.doAction(action);
    },
    sequence: 5,
    sequenceQuick: 30,
});

/** An unknown number: make it a contact, from the form filled with its number and WhatsApp name. */
registerThreadAction("om-whatsapp-create-contact", {
    condition: ({ thread }) => thread?.channel_type === "om_whatsapp" && thread.om_whatsapp_has_contact === false,
    icon: "fa fa-fw fa-user-plus",
    name: _t("Create Contact"),
    open: async ({ thread, owner }) => {
        const { action, orm } = owner.env.services;
        const formAction = await orm.call("discuss.channel", "om_whatsapp_action_create_contact", [[thread.id]]);
        await action.doAction(formAction, {
            onClose: async () => {
                const [values] = await orm.read("discuss.channel", [thread.id], ["name", "om_whatsapp_partner_id"]);
                thread.name = values.name;
                thread.om_whatsapp_has_contact = Boolean(values.om_whatsapp_partner_id);
            },
        });
    },
    sequence: 4,
    sequenceQuick: 35,
});
