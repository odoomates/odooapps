import { AvatarCardPopover } from "@mail/discuss/web/avatar_card/avatar_card_popover";
import { onWillStart } from "@odoo/owl";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { openWhatsappComposer, WHATSAPP_GROUP } from "../whatsapp_composer";

patch(AvatarCardPopover.prototype, {
    setup() {
        super.setup();
        this.action = useService("action");
        onWillStart(async () => {
            this.canWhatsapp = await user.hasGroup(WHATSAPP_GROUP);
        });
    },
    get showWhatsappButton() {
        return Boolean(this.canWhatsapp && this.partner?.id && this.phone);
    },
    onClickWhatsapp() {
        const partnerId = this.partner.id;
        this.props.close();
        openWhatsappComposer(this.action, { resModel: "res.partner", resIds: [partnerId] });
    },
});
