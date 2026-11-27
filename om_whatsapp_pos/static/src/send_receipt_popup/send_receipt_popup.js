import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { SendReceiptPopup } from "@point_of_sale/app/components/popups/send_receipt_popup/send_receipt_popup";

const WHATSAPP_ACTION = "action_send_receipt_om_whatsapp";

patch(SendReceiptPopup.prototype, {
    setup() {
        super.setup(...arguments);
        this.notification = useService("notification");
    },
    showPhoneInput() {
        return super.showPhoneInput() || this.pos.config.om_whatsapp_receipt;
    },
    get isValidWhatsAppNumber() {
        // a local number is formatted with the country of the company
        const digits = (this.state.phone || "").replace(/[\s.\-()]/g, "");
        return /^\+?\d{6,18}$/.test(digits);
    },
    actionSendReceiptOnWhatsApp() {
        this.sendReceipt.call({
            action: WHATSAPP_ACTION,
            destination: this.state.phone,
            name: "WhatsApp",
        });
    },
    async _sendReceiptToCustomer({ action, destination }) {
        if (action !== WHATSAPP_ACTION || !this.order.isSynced) {
            return super._sendReceiptToCustomer(...arguments);
        }
        const result = await this.pos.data.call("pos.order", action, [[this.order.id], destination]);
        if (result?.url) {
            window.open(result.url, "_blank");
        }
        if (result?.error) {
            this.notification.add(result.error, { type: "danger", title: _t("WhatsApp") });
            throw new Error(result.error);
        }
    },
    get sendList() {
        const list = super.sendList;
        if (this.pos.config.om_whatsapp_receipt) {
            list.find((item) => item.model === "phone").buttons.push({
                click: () => this.actionSendReceiptOnWhatsApp(),
                status: this.sendReceipt.lastArgs?.[0]?.name == "WhatsApp" && this.sendReceipt.status,
                icon: "chat_bubble",
                iconClass: "oi-lg o_om_whatsapp_pos_button",
                disabled: () => !this.isValidWhatsAppNumber,
            });
        }
        return list;
    },
});
