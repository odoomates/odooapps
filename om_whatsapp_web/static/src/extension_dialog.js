import { Component, signal, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * Shown when Send is clicked and the extension does not answer on this page:
 * it is not installed, or this Odoo is not allowed in it yet.
 */
export class ExtensionMissingDialog extends Component {
    static template = "om_whatsapp_web.ExtensionMissingDialog";
    static components = { Dialog };
    props = useProps({
        close: t.function(),
        retry: t.function(), // resolves to whether the extension answered
        openWhatsappWeb: t.function(),
        cancel: t.function(),
    });

    setup() {
        this.title = _t("Allow WhatsApp Web sending");
        this.stillMissing = signal(false);
        this.busy = signal(false);
        this.env.dialogData.dismiss = () => this.onCancel();
    }

    async onRetry() {
        this.busy.set(true);
        try {
            if (await this.props.retry()) {
                this.props.close();
            } else {
                this.stillMissing.set(true);
            }
        } finally {
            this.busy.set(false);
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
