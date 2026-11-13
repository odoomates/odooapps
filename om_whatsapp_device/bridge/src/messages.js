// What a WhatsApp message is for Odoo: the items of om_whatsapp_device, the
// same as the ones of the browser extension of om_whatsapp_web.
import {
    getContentType,
    isJidGroup,
    isJidNewsletter,
    isJidStatusBroadcast,
    isLidUser,
    isPnUser,
    jidDecode,
    normalizeMessageContent,
} from "@whiskeysockets/baileys";

// kinds of messages that come with their file, by the type Odoo knows them
export const MEDIA = {
    imageMessage: "image",
    documentMessage: "document",
    stickerMessage: "sticker",
    audioMessage: "audio",
    videoMessage: "video",
};
// kinds that come as a note, without their content
const NOTES = {
    locationMessage: "Location",
    liveLocationMessage: "Location",
    contactMessage: "Contact card",
    contactsArrayMessage: "Contact cards",
    pollCreationMessage: "Poll",
    pollCreationMessageV3: "Poll",
};
const NAMES = { image: "photo", sticker: "sticker", ptt: "voice-message", audio: "audio", video: "video" };
const EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "video/mp4": "mp4",
};
export const MAX_MEDIA_SIZE = 16 * 1024 * 1024;

/** Whether the chat is with one person: not a group, the status, a channel. */
export function isPersonalChat(jid) {
    return Boolean(jid) && !isJidGroup(jid) && !isJidStatusBroadcast(jid) && !isJidNewsletter(jid);
}

/**
 * Digits of the phone number of a chat with one person, else null. A chat
 * addressed by a hidden id (@lid) gives its number by the other id of its
 * key, else by the mapping WhatsApp keeps.
 */
export async function phoneOf(sock, jid, alt) {
    if (!isPersonalChat(jid)) {
        return null;
    }
    if (isPnUser(jid)) {
        return jidDecode(jid)?.user || null;
    }
    if (isLidUser(jid)) {
        if (alt && isPnUser(alt)) {
            return jidDecode(alt)?.user || null;
        }
        try {
            const pn = await sock.signalRepository?.lidMapping?.getPNForLID(jid);
            if (pn) {
                return jidDecode(pn)?.user || null;
            }
        } catch {
            // no mapping
        }
    }
    return null;
}

function contextOf(content) {
    for (const value of Object.values(content || {})) {
        if (value && typeof value === "object" && value.contextInfo) {
            return value.contextInfo;
        }
    }
    return null;
}

/**
 * The item of a message, or null for what Odoo does not take: groups,
 * status, channels, reactions (see reactionItem), system messages. Its file
 * is fetched apart (fileOf), when it has one.
 */
export async function messageItem(sock, msg) {
    const key = msg.key || {};
    if (!key.id || !msg.message) {
        return null;
    }
    const phone = await phoneOf(sock, key.remoteJid, key.remoteJidAlt);
    if (!phone) {
        return null;
    }
    const content = normalizeMessageContent(msg.message);
    const kind = getContentType(content);
    if (!kind || kind === "reactionMessage" || kind === "protocolMessage" || kind === "senderKeyDistributionMessage") {
        return null;
    }
    const item = {
        kind: "message",
        id: key.id,
        phone,
        from_me: Boolean(key.fromMe),
        type: kind.replace(/Message$/, ""),
        t: Number(msg.messageTimestamp || 0),
        body: "",
        quoted_id: contextOf(content)?.stanzaId || null,
        name: (!key.fromMe && msg.pushName) || null,
    };
    const inner = content[kind];
    if (kind === "conversation") {
        item.type = "chat";
        item.body = inner || "";
    } else if (kind === "extendedTextMessage") {
        item.type = "chat";
        item.body = inner?.text || "";
    } else if (MEDIA[kind]) {
        item.type = kind === "audioMessage" && inner?.ptt ? "ptt" : MEDIA[kind];
        item.body = inner?.caption || "";
        item.has_media = true;
        item.size = Number(inner?.fileLength || 0);
    } else if (NOTES[kind]) {
        item.note = NOTES[kind];
        if (kind === "locationMessage" && inner) {
            const place = [inner.name, inner.address].filter(Boolean).join(" ");
            item.body = `${place} https://maps.google.com/?q=${inner.degreesLatitude},${inner.degreesLongitude}`.trim();
        }
    } else if (kind === "buttonsResponseMessage" || kind === "templateButtonReplyMessage") {
        item.type = "chat";
        item.body = inner?.selectedDisplayText || inner?.selectedButtonId || "";
    } else if (kind === "listResponseMessage") {
        item.type = "chat";
        item.body = inner?.title || "";
    } else {
        return null;
    }
    return item;
}

/** The name and mimetype of the file of a message. */
export function fileNameOf(msg, item) {
    const content = normalizeMessageContent(msg.message);
    const inner = content?.[getContentType(content)] || {};
    const mimetype = (inner.mimetype || "application/octet-stream").split(";")[0];
    const extension = EXTENSIONS[mimetype] || "bin";
    return { name: inner.fileName || `${NAMES[item.type] || "whatsapp"}-${item.id}.${extension}`, mimetype };
}

/** The item of a reaction to a message: its emoji, empty when taken back. */
export async function reactionItem(sock, { key, reaction }) {
    const phone = await phoneOf(sock, key?.remoteJid, key?.remoteJidAlt);
    if (!phone || !key?.id) {
        return null;
    }
    const fromMe = Boolean(reaction?.key?.fromMe);
    return {
        kind: "reaction",
        id: `${key.id}:${fromMe ? "me" : phone}`,
        message_id: key.id,
        phone,
        from_me: fromMe,
        emoji: reaction?.text || "",
    };
}

// the ack of WhatsApp for a message sent, as the status of Odoo
const STATUS = { 0: "failed", 2: "sent", 3: "delivered", 4: "read", 5: "read" };

/** The item of a status update of a message sent. */
export async function statusItem(sock, { key, update }) {
    const status = STATUS[update?.status];
    if (!status || !key?.fromMe || !key.id || !isPersonalChat(key.remoteJid)) {
        return null;
    }
    return { kind: "status", id: key.id, status };
}
