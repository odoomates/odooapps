import { _t } from "@web/core/l10n/translation";
import { onWillStart } from "@odoo/owl";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { formPhoneField, PhoneField, phoneField } from "@web/views/fields/phone/phone_field";
import { openWhatsappComposer, WHATSAPP_GROUP } from "../whatsapp_composer";

patch(PhoneField, {
    defaultProps: {
        ...PhoneField.defaultProps,
        enableWhatsapp: true,
    },
    props: {
        ...PhoneField.props,
        enableWhatsapp: { type: Boolean, optional: true },
    },
});

patch(PhoneField.prototype, {
    setup() {
        super.setup();
        this.action = useService("action");
        onWillStart(async () => {
            this.canWhatsapp = await user.hasGroup(WHATSAPP_GROUP);
        });
    },
    get showWhatsapp() {
        return Boolean(this.props.enableWhatsapp && this.canWhatsapp && this.props.record.data[this.props.name]);
    },
    async onClickWhatsapp() {
        const record = this.props.record;
        const number = record.data[this.props.name];
        if (!(await record.save()) || !record.resId) {
            return;
        }
        openWhatsappComposer(this.action, {
            resModel: record.resModel,
            resIds: [record.resId],
            number,
            onClose: () => record.load(),
        });
    },
});

const descriptionPatch = (description) => ({
    extractProps({ options }) {
        const props = super.extractProps(...arguments);
        props.enableWhatsapp = options.enable_whatsapp;
        return props;
    },
    supportedOptions: [
        ...(description.supportedOptions || []),
        {
            label: _t("Enable WhatsApp"),
            name: "enable_whatsapp",
            type: "boolean",
            default: true,
        },
    ],
});

patch(phoneField, descriptionPatch(phoneField));
patch(formPhoneField, descriptionPatch(formPhoneField));
