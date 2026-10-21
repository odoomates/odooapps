/** @odoo-module **/

import { ChatterTopbar } from "@mail/components/chatter_topbar/chatter_topbar";
import { patch } from "web.utils";
import session from "web.session";
import { WHATSAPP_GROUP, whatsappComposerAction } from "../whatsapp_composer";

const { onWillStart } = owl.hooks;

/** The WhatsApp button of the chatter: the composer on the document. */
patch(ChatterTopbar.prototype, "om_whatsapp_base", {
    setup() {
        this._super(...arguments);
        onWillStart(async () => {
            this.canWhatsapp = await session.user_has_group(WHATSAPP_GROUP);
        });
    },
    onClickWhatsapp() {
        const thread = this.chatter && this.chatter.thread;
        if (!thread || thread.isTemporary) {
            return;
        }
        this.env.bus.trigger("do-action", {
            action: whatsappComposerAction({ resModel: thread.model, resIds: [thread.id] }),
            options: {
                on_close: () => {
                    if (thread.exists()) {
                        thread.refresh();
                    }
                },
            },
        });
    },
});
