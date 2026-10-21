import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { ExtensionMissingDialog } from "./extension_dialog";
import { getExtensionVersion, sendThroughExtension } from "./extension_bridge";

const MODEL = "mail.notification";

async function readAsBase64(attachmentId) {
    const response = await fetch(`/web/content/${attachmentId}?download=true`);
    if (!response.ok) {
        throw new Error(_t("The file could not be read from Odoo."));
    }
    const blob = await response.blob();
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",", 2)[1]);
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(blob);
    });
}

async function sendOne(payload) {
    try {
        const attachments = await Promise.all(
            payload.attachments.map(async (attachment) => ({
                name: attachment.name,
                mimetype: attachment.mimetype,
                data: await readAsBase64(attachment.id),
            }))
        );
        const answer = await sendThroughExtension({ ...payload, attachments });
        if (answer.ok) {
            return { error: false, whatsappId: answer.whatsapp_ids?.[0] || false };
        }
        return { error: answer.error || _t("WhatsApp Web did not send the message.") };
    } catch (error) {
        return { error: error.message === "timeout" ? _t("WhatsApp Web did not answer in time.") : error.message };
    }
}

// Sends still running in this page: leaving it would lose their result.
const pending = new Set();

window.addEventListener("beforeunload", (event) => {
    if (pending.size) {
        event.preventDefault();
    }
});

// Messages sent one after the other to the same contact share their notices:
// one "Sending..." while they go, one "sent" once the line is empty or the
// next message is for someone else. A failure is told on its own.
let batch = null;

function startBatch(notification, recipient) {
    if (batch?.recipient === recipient) {
        return;
    }
    endBatch(notification);
    const closeSending = notification.add(_t("Sending through WhatsApp Web..."), { type: "info" });
    batch = { recipient, sent: 0, closeSending };
}

function endBatch(notification) {
    if (!batch) {
        return;
    }
    const { recipient, sent, closeSending } = batch;
    batch = null;
    if (typeof closeSending === "function") {
        closeSending();
    }
    if (sent === 1) {
        notification.add(_t("WhatsApp sent to %(recipient)s.", { recipient }), { type: "success" });
    } else if (sent > 1) {
        notification.add(_t("%(count)s WhatsApp messages sent to %(recipient)s.", { count: sent, recipient }), {
            type: "success",
        });
    }
}

async function sendInBackground({ orm, notification }, notificationIds) {
    try {
        // none when another browser open on this Odoo took them first
        const payloads = await orm.call(MODEL, "om_whatsapp_web_payload", [notificationIds]);
        for (const payload of payloads) {
            startBatch(notification, payload.recipient);
            const { error, whatsappId } = await sendOne(payload);
            await orm.call(MODEL, "om_whatsapp_web_done", [[payload.id]], {
                error,
                ...(whatsappId ? { whatsapp_id: whatsappId } : {}),
            });
            if (error) {
                notification.add(
                    _t("WhatsApp to %(recipient)s not sent: %(reason)s", { recipient: payload.recipient, reason: error }),
                    { type: "danger", sticky: true }
                );
            } else {
                batch.sent++;
            }
        }
    } catch (error) {
        notification.add(_t("WhatsApp message not sent: %(reason)s", { reason: error.data?.message || error.message }), {
            type: "danger",
            sticky: true,
        });
    }
}

// The sends of this page, one after the other in the order they were asked:
// messages typed fast in a conversation go out in that order, and each waits
// for the extension only once its turn comes.
let lastTurn = Promise.resolve();

/** A place in the line, taken at once; ``release`` lets the next one go. */
function takeTurn() {
    let release;
    const done = new Promise((resolve) => (release = resolve));
    const ready = lastTurn;
    lastTurn = lastTurn.then(() => done);
    return { ready, release };
}

function startSending({ orm, notification }, notificationIds, turn) {
    const job = turn.ready.then(() => sendInBackground({ orm, notification }, notificationIds)).finally(turn.release);
    pending.add(job);
    job.finally(() => {
        pending.delete(job);
        if (!pending.size) {
            endBatch(notification);
        }
    });
}

/**
 * Returned by the WhatsApp Web provider for the queued messages. The dialog
 * closes at once; the messages go to the extension in the background, and a
 * notification tells how each one went. When the extension does not answer,
 * a dialog asks to allow this Odoo in it, or to open the chat in WhatsApp Web
 * for the user to send.
 */
export async function sendWhatsappWeb(env, action) {
    const { orm, notification, dialog } = env.services;
    const notificationIds = action.params.notification_ids;
    const turn = takeTurn();
    if (await getExtensionVersion()) {
        startSending({ orm, notification }, notificationIds, turn);
    } else {
        turn.release();
        dialog.add(ExtensionMissingDialog, {
            retry: async () => {
                if (!(await getExtensionVersion())) {
                    return false;
                }
                startSending({ orm, notification }, notificationIds, takeTurn());
                return true;
            },
            openWhatsappWeb: async () =>
                env.services.action.doAction(await orm.call(MODEL, "om_whatsapp_web_fallback", [notificationIds])),
            cancel: () => orm.call(MODEL, "om_whatsapp_web_cancel", [notificationIds]),
        });
    }
    return { type: "ir.actions.act_window_close" };
}

registry.category("actions").add("om_whatsapp_web_send", sendWhatsappWeb);
