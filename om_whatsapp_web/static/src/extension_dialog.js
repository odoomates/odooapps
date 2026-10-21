import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * Shown when Send is clicked and the extension does not answer on this page:
 * it is not installed, or this Odoo is not allowed in it yet.
 */
export class ExtensionMissingDialog extends Component {
    static template = "om_whatsapp_web.ExtensionMissingDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        retry: Function, // resolves to whether the extension answered
        openWhatsappWeb: Function,
        cancel: Function,
    };

    setup() {
        this.title = _t("Allow WhatsApp Web sending");
        this.state = useState({ stillMissing: false, busy: false });
        this.env.dialogData.dismiss = () => this.onCancel();
    }

    async onRetry() {
        this.state.busy = true;
        try {
            if (await this.props.retry()) {
                this.props.close();
            } else {
                this.state.stillMissing = true;
            }
        } finally {
            this.state.busy = false;
        }
    }

    async onOpenWhatsappWeb() {
        this.props.close();
        await this.props.openWhatsappWeb();
    }

    async onCancel() {
        this.props.close();
        await this.props.cancel();
    }
}
