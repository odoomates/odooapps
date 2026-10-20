import { threadActionsRegistry } from "@mail/core/common/thread_actions";
import { _t } from "@web/core/l10n/translation";

/** The document a WhatsApp conversation last spoke about, from its header. */
threadActionsRegistry.add("om-whatsapp-document", {
    condition: (component) =>
        component.thread?.channel_type === "om_whatsapp" && Boolean(component.thread.om_whatsapp_document_name),
    icon: "fa fa-fw fa-file-text-o",
    name: (component) => _t("Open %(document)s", { document: component.thread.om_whatsapp_document_name }),
    async open(component) {
        const action = await component.env.services.orm.call(
            "discuss.channel",
            "om_whatsapp_action_open_document",
            [[component.thread.id]]
        );
        await component.env.services.action.doAction(action);
    },
    sequence: 5,
    sequenceQuick: 30,
});

/** An unknown number: make it a contact, from the form filled with its number and WhatsApp name. */
threadActionsRegistry.add("om-whatsapp-create-contact", {
    condition: (component) =>
        component.thread?.channel_type === "om_whatsapp" && component.thread.om_whatsapp_has_contact === false,
    icon: "fa fa-fw fa-user-plus",
    name: _t("Create Contact"),
    async open(component) {
        const thread = component.thread;
        const { action, orm } = component.env.services;
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
