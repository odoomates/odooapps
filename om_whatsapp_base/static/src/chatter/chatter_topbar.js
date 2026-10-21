/** @odoo-module **/

import { ChatterTopbar } from "@mail/components/chatter_topbar/chatter_topbar";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { openWhatsappComposer, WHATSAPP_GROUP } from "../whatsapp_composer";

const { onWillStart } = owl;

/** The WhatsApp button of the chatter: the composer on the document, saved first when new. */
patch(ChatterTopbar.prototype, "om_whatsapp_base.ChatterTopbar", {
    setup() {
        this._super(...arguments);
        this.action = useService("action");
        const user = useService("user");
        onWillStart(async () => {
            this.canWhatsapp = await user.hasGroup(WHATSAPP_GROUP);
        });
    },
    async onClickWhatsapp() {
        const chatter = this.chatterTopbar.chatter;
        if (chatter.isTemporary && !(await chatter.doSaveRecord())) {
            return;
        }
        const thread = chatter.thread;
        openWhatsappComposer(this.action, {
            resModel: thread.model,
            resIds: [thread.id],
            onClose: () => {
                if (thread.exists()) {
                    thread.fetchData(["messages"]);
                }
            },
        });
    },
});
