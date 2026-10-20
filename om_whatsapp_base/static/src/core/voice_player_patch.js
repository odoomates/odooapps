/** @odoo-module **/

import { VoicePlayer } from "@mail/discuss/voice_message/common/voice_player";
import { patch } from "@web/core/utils/patch";

// the files already told, in this page
const told = new Set();

/** A voice message played in Odoo: WhatsApp shows it played, when it came from WhatsApp. */
patch(VoicePlayer.prototype, {
    onClickPlayPause() {
        const starting = this.state.paused && !this.props.attachment?.uploading;
        super.onClickPlayPause(...arguments);
        const id = this.props.attachment?.id;
        if (starting && id && !told.has(id)) {
            told.add(id);
            this.env.services.orm.silent
                .call("mail.message", "om_whatsapp_played", [id])
                .catch(() => told.delete(id));
        }
    },
});
