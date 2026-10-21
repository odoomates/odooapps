import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { fetchMedia, getExtensionInfo, inboxDone, onInboxWake, onStatusWake, takeInbox } from "./extension_bridge";

const ACCOUNT = "om.whatsapp.account";
const POLL_DELAY = 20000;
// how often to look for the extension again when it is not in this page
const PING_DELAY = 60000;
// a file that cannot be read is tried again on the next look, then the message is recorded without it
const MEDIA_TRIES = 2;
// while WhatsApp Web is closed or loading, a file waits for it this long (seconds), without counting as a try
const MEDIA_WAIT = 24 * 3600;

/**
 * Takes the messages the extension read in WhatsApp Web and has Odoo record
 * those of the numbers it knows. Only their numbers reach Odoo first: the
 * others are dropped in the browser, with their text and files.
 */
export class WhatsappReceiver {
    constructor(orm, notification) {
        this.orm = orm;
        this.notification = notification;
        this.mediaTries = new Map();
        this.running = null;
        this.toldNumber = null;
    }

    /** Tell the user once why the messages of this WhatsApp are not brought in. */
    tellNoAccount(me) {
        if (this.toldNumber === me) {
            return;
        }
        this.toldNumber = me;
        this.notification?.add(
            _t(
                "The WhatsApp linked in this browser (+%(number)s) is not the WhatsApp Number of your WhatsApp Web account in Odoo: its messages are kept in the extension until the number of the account is set to it.",
                { number: me }
            ),
            { type: "warning", sticky: true }
        );
    }

    /** One look at the inbox of the extension, one at a time. Resolves to the number of items recorded. */
    pull() {
        this.running ??= this._pull().finally(() => (this.running = null));
        return this.running;
    }

    async _pull() {
        const answer = await takeInbox();
        const items = answer?.items || [];
        if (!answer?.ok || !answer.me || !items.length) {
            return 0;
        }
        const numbers = items
            .filter((item) => item.kind === "message")
            .map(({ id, kind, phone, quoted_id, t }) => ({ id, kind, phone, quoted_id, t }));
        const { account, accept } = await this.orm.call(ACCOUNT, "om_whatsapp_web_accept", [answer.me, numbers]);
        if (!account) {
            // the WhatsApp linked in this browser is not one of the accounts of the
            // user: keep the messages in the extension until the account is fixed
            this.tellNoAccount(answer.me);
            return 0;
        }
        this.toldNumber = null;
        const accepted = new Set(accept);
        const dropped = [];
        const plain = [];
        const withMedia = [];
        for (const item of items) {
            if (item.kind === "message" && !accepted.has(item.id)) {
                dropped.push(item.key);
            } else if (item.has_media) {
                withMedia.push(item);
            } else {
                plain.push(item);
            }
        }
        // what needs no file goes at once: a file never holds the others back
        if (plain.length) {
            await this.orm.call(ACCOUNT, "om_whatsapp_web_receive", [answer.me, plain]);
        }
        await inboxDone([...dropped, ...plain.map((item) => item.key)]);
        let recorded = plain.length;
        for (const item of withMedia) {
            const record = { ...item };
            const media = await fetchMedia(item.id).catch((error) => ({ ok: false, error: error.message }));
            if (media.ok) {
                record.media = { name: media.name, mimetype: media.mimetype, data: media.data };
            } else if (media.retry && (!item.t || Date.now() / 1000 - item.t < MEDIA_WAIT)) {
                continue; // left in the extension until WhatsApp Web is open again
            } else {
                const tries = (this.mediaTries.get(item.key) || 0) + 1;
                if (tries < MEDIA_TRIES) {
                    this.mediaTries.set(item.key, tries);
                    continue; // left in the extension, for the next look
                }
                record.media_error = media.error || "timeout";
            }
            this.mediaTries.delete(item.key);
            await this.orm.call(ACCOUNT, "om_whatsapp_web_receive", [answer.me, [record]]);
            await inboxDone([item.key]);
            recorded++;
        }
        return recorded;
    }
}

/**
 * In every page of the users of WhatsApp: looks at the inbox of the extension
 * when it has read something, and every POLL_DELAY anyway.
 */
export const whatsappReceiveService = {
    dependencies: ["orm", "notification"],
    start(env, { orm, notification }) {
        const receiver = new WhatsappReceiver(orm, notification);
        let ready = false;
        let lastPing = 0;
        const look = async () => {
            if (!ready) {
                if (Date.now() - lastPing < PING_DELAY) {
                    return;
                }
                lastPing = Date.now();
                ready = Boolean((await getExtensionInfo())?.features.includes("receive"));
                if (!ready) {
                    return;
                }
            }
            try {
                await receiver.pull();
            } catch (error) {
                console.warn("WhatsApp messages not taken from the extension:", error);
            }
        };
        user.hasGroup("om_whatsapp_base.group_om_whatsapp_user").then((allowed) => {
            if (allowed) {
                onInboxWake(look);
                // WhatsApp Web open and synced again: what waited in the extension comes now
                onStatusWake(look);
                setInterval(look, POLL_DELAY);
                setTimeout(look, 3000);
            }
        });
        return receiver;
    },
};

registry.category("services").add("om_whatsapp_web_receive", whatsappReceiveService);
