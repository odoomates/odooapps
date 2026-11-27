import { VoicePlayer } from "@mail/discuss/voice_message/common/voice_player";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";

// the files already told, in this page
const told = new Set();

/** A voice message played in Odoo: the channel shows it played, when it came from there. */
patch(VoicePlayer.prototype, {
    async onClickPlayPause() {
        await super.onClickPlayPause(...arguments);
        const id = this.props.attachment?.id;
        if (this.state.playing && id && !told.has(id)) {
            told.add(id);
            rpc("/web/dataset/call_kw/mail.message/om_social_played", {
                model: "mail.message",
                method: "om_social_played",
                args: [id],
                kwargs: {},
            }).catch(() => told.delete(id));
        }
    },
});
