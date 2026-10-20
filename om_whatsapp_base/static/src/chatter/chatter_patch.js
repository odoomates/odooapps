import { Chatter } from "@mail/chatter/web_portal_project/chatter";
import { onWillStart } from "@odoo/owl";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { openWhatsappComposer, WHATSAPP_GROUP } from "../whatsapp_composer";

patch(Chatter.prototype, {
    setup() {
        super.setup();
        this.action = useService("action");
        onWillStart(async () => {
            this.canWhatsapp = await user.hasGroup(WHATSAPP_GROUP);
        });
    },
    onClickWhatsapp() {
        const open = (thread) =>
            openWhatsappComposer(this.action, {
                resModel: thread.model,
                resIds: [thread.id],
                onClose: () => this.load(thread, ["messages"]),
            });
        if (this.state.thread.id) {
            open(this.state.thread);
        } else {
            // a new record: the chatter calls this once the record is saved
            this.onThreadCreated = open;
            this.webChatterProps.saveRecord?.();
        }
    },
});
