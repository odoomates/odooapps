/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

const { useState } = owl.hooks;

/**
 * Shown when Send is clicked and the extension does not answer on this page:
 * it is not installed, or this Odoo is not allowed in it yet.
 */
export class ExtensionMissingDialog extends Dialog {
    setup() {
        super.setup();
        this.title = _t("Allow WhatsApp Web sending");
        this.state = useState({ stillMissing: false, busy: false });
    }

    async onRetry() {
        this.state.busy = true;
        try {
            if (await this.props.retry()) {
                this.props.handled();
                this.close();
            } else {
                this.state.stillMissing = true;
            }
        } finally {
            this.state.busy = false;
        }
    }

    async onOpenWhatsappWeb() {
        this.props.handled();
        this.close();
        await this.props.openWhatsappWeb();
    }

    async onCancel() {
        this.props.handled();
        this.close();
        await this.props.cancel();
    }
}
ExtensionMissingDialog.size = "modal-md";
ExtensionMissingDialog.technical = false;
ExtensionMissingDialog.bodyTemplate = "om_whatsapp_web.ExtensionMissingDialogBody";
ExtensionMissingDialog.footerTemplate = "om_whatsapp_web.ExtensionMissingDialogFooter";
