import { Composer } from "@mail/core/common/composer";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

const { DateTime } = luxon;

/** In a WhatsApp conversation whose 24 hours are over, the message box says why free text is refused. */
patch(Composer.prototype, {
    get placeholder() {
        const until = this.thread?.om_whatsapp_free_text_until;
        if (!this.props.placeholder && until && deserializeDateTime(until) < DateTime.now()) {
            return _t("24 hours since the last message of the contact: send an approved template from the contact or the document");
        }
        return super.placeholder;
    },
});
