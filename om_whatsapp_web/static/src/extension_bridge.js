// Talks to the Odoo Mates WhatsApp Connector extension through window.postMessage.
// Both sides post JSON strings, which Chrome and Firefox pass to content scripts
// as they are. The protocol is described in PROTOCOL.md of the extension.

const PAGE = "om-whatsapp-web";
const EXTENSION = "om-whatsapp-extension";
const PROTOCOL = 1;
const PING_TIMEOUT = 500;
const SEND_TIMEOUT = 120000;
const REACT_TIMEOUT = 30000;
const STATUS_TIMEOUT = 4000;
const INBOX_TIMEOUT = 10000;
const MEDIA_TIMEOUT = 60000;

let lastId = 0;

function request(type, data, timeout) {
    const id = `${Date.now()}-${++lastId}`;
    return new Promise((resolve, reject) => {
        const onMessage = (event) => {
            if (event.source !== window || typeof event.data !== "string") {
                return;
            }
            let answer;
            try {
                answer = JSON.parse(event.data);
            } catch {
                return;
            }
            if (answer?.source === EXTENSION && answer.id === id) {
                stop();
                resolve(answer);
            }
        };
        const timer = setTimeout(() => {
            stop();
            reject(new Error("timeout"));
        }, timeout);
        const stop = () => {
            clearTimeout(timer);
            window.removeEventListener("message", onMessage);
        };
        window.addEventListener("message", onMessage);
        window.postMessage(
            JSON.stringify({ source: PAGE, protocol: PROTOCOL, id, type, ...data }),
            window.location.origin
        );
    });
}

/** { version, features } of the extension, or null when it does not answer on this page. */
export async function getExtensionInfo() {
    try {
        const answer = await request("ping", {}, PING_TIMEOUT);
        return answer.version ? { version: answer.version, features: answer.features || ["send"] } : null;
    } catch {
        return null;
    }
}

/** The version of the extension, or null when it does not answer on this page. */
export async function getExtensionVersion() {
    return (await getExtensionInfo())?.version || null;
}

/**
 * Send one message: { phone, body, attachments: [{ name, mimetype, data }] },
 * data in base64. Resolves to { ok, error }.
 */
export function sendThroughExtension(message) {
    return request("send", { message }, SEND_TIMEOUT);
}

/**
 * React to a message in WhatsApp Web: { phone, whatsapp_id, emoji }, an empty
 * emoji takes the reaction back. Resolves to { ok, error }.
 */
export function reactThroughExtension(reaction) {
    return request("react", { reaction }, REACT_TIMEOUT);
}

/**
 * Messages and status updates read in WhatsApp Web, kept for this page for a
 * while: { ok, me, items }, ``me`` the number linked in WhatsApp Web.
 */
export function takeInbox() {
    return request("inbox", {}, INBOX_TIMEOUT);
}

/** Tell the extension these items (by ``key``) are dealt with. */
export function inboxDone(keys) {
    return request("inbox-done", { keys }, INBOX_TIMEOUT);
}

/** The file of a message read in WhatsApp Web: { ok, name, mimetype, data, error }, data in base64. */
export function fetchMedia(messageId) {
    return request("media", { message_id: messageId }, MEDIA_TIMEOUT);
}

/**
 * The WhatsApp Web of this browser (extension 1.5.0 or later): { ok, tab,
 * state: "loading" | "qr" | "ready", me, reader, error }.
 */
export function getStatus() {
    return request("status", {}, STATUS_TIMEOUT);
}

/**
 * Mark messages read or played in WhatsApp Web (extension 1.6.0 or later):
 * { phone, ids, kind: "read" | "played" }. Resolves to { ok, error }.
 */
export function sendReceipt(receipt) {
    return request("receipt", { receipt }, REACT_TIMEOUT);
}

/**
 * The WhatsApp profile picture of ``phone`` (extension 1.7.0 or later):
 * { ok, data, mimetype } read in WhatsApp Web, { ok, url } when it could not
 * download it, { ok, none: true } when the customer shows none.
 */
export function getPicture(phone) {
    return request("picture", { phone }, REACT_TIMEOUT);
}

/** Show the WhatsApp Web tab, opened when there is none. */
export function openWhatsappTab() {
    return request("open-tab", {}, STATUS_TIMEOUT);
}

/** Call ``callback`` when the extension has read something new; returns the function that stops it. */
export function onInboxWake(callback) {
    return onExtensionEvent("inbox-wake", callback);
}

/** Call ``callback`` when the status of WhatsApp Web may have changed; returns the function that stops it. */
export function onStatusWake(callback) {
    return onExtensionEvent("status-wake", callback);
}

function onExtensionEvent(type, callback) {
    const onMessage = (event) => {
        if (event.source !== window || typeof event.data !== "string") {
            return;
        }
        let data;
        try {
            data = JSON.parse(event.data);
        } catch {
            return;
        }
        if (data?.source === EXTENSION && data.type === type) {
            callback();
        }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
}
