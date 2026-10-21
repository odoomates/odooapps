/** @odoo-module **/

import { PhoneField } from "@web/views/fields/phone/phone_field";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { openWhatsappComposer, WHATSAPP_GROUP } from "../whatsapp_composer";

const { Component, onWillStart, status } = owl;

/** The WhatsApp button next to a phone number: the composer, to that number. */
export class WhatsappPhoneButton extends Component {
    setup() {
        this.action = useService("action");
        const user = useService("user");
        onWillStart(async () => {
            this.canWhatsapp = await user.hasGroup(WHATSAPP_GROUP);
        });
    }
    async onClick() {
        const record = this.props.record;
        const number = this.props.value;
        if ((await record.save()) === false || !record.resId) {
            return;
        }
        openWhatsappComposer(this.action, {
            resModel: record.resModel,
            resIds: [record.resId],
            number,
            onClose: () => {
                if (status(this) !== "destroyed") {
                    record.load();
                }
            },
        });
    }
}
WhatsappPhoneButton.template = "om_whatsapp_base.WhatsappPhoneButton";
WhatsappPhoneButton.props = ["*"];

patch(PhoneField, "om_whatsapp_base.PhoneField", {
    components: { ...PhoneField.components, WhatsappPhoneButton },
});
