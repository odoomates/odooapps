import { _t } from "@web/core/l10n/translation";
import { onWillStart, t } from "@odoo/owl";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { PhoneField, phoneField, phoneFieldProps } from "@web/views/fields/phone/phone_field";
import { openWhatsappComposer, WHATSAPP_GROUP } from "../whatsapp_composer";

Object.assign(phoneFieldProps, {
    enableWhatsapp: t.boolean().optional(true),
});

patch(PhoneField.prototype, {
    setup() {
        super.setup();
        this.action = useService("action");
        onWillStart(async () => {
            this.canWhatsapp = await user.hasGroup(WHATSAPP_GROUP);
        });
    },
    get actionButtons() {
        const buttons = super.actionButtons;
        if (!this.props.enableWhatsapp || !this.canWhatsapp || !this.value) {
            return buttons;
        }
        return [
            ...buttons,
            {
                icon: "oi_whatsapp",
                name: _t("WhatsApp"),
                onSelected: async () => {
                    const record = this.props.record;
                    if (!(await record.save()) || !record.resId) {
                        return;
                    }
                    openWhatsappComposer(this.action, {
                        resModel: record.resModel,
                        resIds: [record.resId],
                        number: this.value,
                        onClose: () => record.load(),
                    });
                },
            },
        ];
    },
});

patch(phoneField, {
    extractProps({ options }) {
        const props = super.extractProps(...arguments);
        props.enableWhatsapp = options.enable_whatsapp;
        return props;
    },
    supportedOptions: [
        ...(phoneField.supportedOptions || []),
        {
            label: _t("Enable WhatsApp"),
            name: "enable_whatsapp",
            type: "boolean",
            default: true,
        },
    ],
});
