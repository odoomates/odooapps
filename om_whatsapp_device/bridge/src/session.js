// One WhatsApp linked device: the session of one account of Odoo. It shows
// a QR code (or a pairing code) until the phone links it, keeps connected,
// hands what comes in to Odoo, and sends one message at a time, with a pause
// of a person between two.
import { chmod, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { DisconnectReason, downloadMediaMessage, jidDecode } from "@whiskeysockets/baileys";
import QRCode from "qrcode";
import { fileNameOf, MAX_MEDIA_SIZE, messageItem, reactionItem, statusItem } from "./messages.js";

const TOO_BIG = "The file is too big.";

/** The content of ``stream``, up to ``limit`` bytes: the size a sender gives
 * may be false, the file is not read past the limit. */
export async function readLimited(stream, limit) {
    const chunks = [];
    let size = 0;
    for await (const chunk of stream) {
        size += chunk.length;
        if (size > limit) {
            stream.destroy();
            throw new Error(TOO_BIG);
        }
        chunks.push(chunk);
    }
    return Buffer.concat(chunks);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const MAX_RECONNECT_DELAY = 60000;

const MAX_PICTURE_SIZE = 2 * 1024 * 1024;

export class Session {
    /**
     * @param {string} key the session of the account, as Odoo names it
     * @param {object} options
     * @param {string} options.dataDir where the keys of the linked device are kept
     * @param {Function} options.createSocket (auth, logger) => a Baileys socket
     * @param {Function} options.loadAuth (folder) => {state, saveCreds}
     * @param {Function} options.notify (key, items) => hands items to Odoo
     * @param {object} options.logger
     * @param {Function} [options.download] (msg, sock) => the file of a message, a Buffer
     */
    constructor(key, { dataDir, createSocket, loadAuth, notify, logger, download }) {
        this.key = key;
        this.folder = path.join(dataDir, key);
        this.createSocket = createSocket;
        this.loadAuth = loadAuth;
        this.notify = notify;
        this.logger = logger;
        this.download = download || ((msg, sock) =>
            downloadMediaMessage(msg, "stream", {}, { logger, reuploadRequest: sock.updateMediaMessage })
                .then((stream) => readLimited(stream, MAX_MEDIA_SIZE)));
        this.config = { webhook_url: null, database: null, min_gap: 2000, max_gap: 6000, pairing_phone: null };
        this.state = "stopped";
        this.qr = null;
        this.qrImage = null;
        this.pairingCode = null;
        this.me = null;
        this.reason = null;
        this.sock = null;
        this.retries = 0;
        this.stopping = false;
        this.queue = Promise.resolve();
        this.lastSent = 0;
    }

    get status() {
        return {
            key: this.key,
            state: this.state,
            qr: this.qr,
            // drawn here: Odoo shows it as it is, whatever its server has to draw images
            qr_image: this.qr ? this.qrImage : null,
            pairing_code: this.pairingCode,
            me: this.me,
            reason: this.reason,
        };
    }

    async saveConfig(config) {
        Object.assign(this.config, config);
        await mkdir(this.folder, { recursive: true, mode: 0o700 });
        await chmod(this.folder, 0o700); // made by an older version, open to all
        await writeFile(path.join(this.folder, "odoo.json"), JSON.stringify(this.config), { mode: 0o600 });
    }

    async loadConfig() {
        try {
            Object.assign(this.config, JSON.parse(await readFile(path.join(this.folder, "odoo.json"), "utf8")));
            return true;
        } catch {
            return false;
        }
    }

    setState(state, values = {}) {
        Object.assign(this, values);
        this.state = state;
        this.notify(this.key, [{ kind: "state", ...this.status }]);
    }

    async start() {
        this.stopping = false;
        await mkdir(this.folder, { recursive: true, mode: 0o700 });
        await chmod(this.folder, 0o700); // made by an older version, open to all
        const { state, saveCreds } = await this.loadAuth(path.join(this.folder, "auth"));
        const sock = await this.createSocket(state, this.logger);
        this.sock = sock;
        this.pairingRequested = false;
        this.setState(state.creds?.registered ? "connecting" : "starting", { qr: null, reason: null });
        sock.ev.on("creds.update", saveCreds);
        sock.ev.on("connection.update", (update) => this.onConnection(sock, update));
        sock.ev.on("messages.upsert", (event) => this.onMessages(sock, event));
        sock.ev.on("messages.update", (updates) => this.onUpdates(sock, updates));
        sock.ev.on("messages.reaction", (reactions) => this.onReactions(sock, reactions));
    }

    async onConnection(sock, { connection, lastDisconnect, qr }) {
        if (sock !== this.sock) {
            return;
        }
        if (qr) {
            if (this.config.pairing_phone && !this.pairingRequested) {
                this.pairingRequested = true;
                try {
                    const code = await sock.requestPairingCode(this.config.pairing_phone);
                    this.setState("pairing", { pairingCode: code, qr: null });
                } catch (error) {
                    this.setState("qr", { qr, reason: `No pairing code: ${error.message}` });
                }
            } else if (!this.config.pairing_phone) {
                const qrImage = await QRCode.toDataURL(qr, { width: 300, margin: 1 }).catch(() => null);
                this.setState("qr", { qr, qrImage });
            }
        }
        if (connection === "open") {
            this.retries = 0;
            this.setState("open", { qr: null, pairingCode: null, reason: null, me: jidDecode(sock.user?.id)?.user || null });
        } else if (connection === "close") {
            const code = lastDisconnect?.error?.output?.statusCode;
            if (this.stopping) {
                this.setState("stopped");
            } else if (code === DisconnectReason.loggedOut) {
                // unlinked from the phone: the keys are of no use any more
                await rm(path.join(this.folder, "auth"), { recursive: true, force: true });
                this.setState("logged_out", { me: null, qr: null, reason: "Unlinked from the phone." });
            } else {
                const delay = code === DisconnectReason.restartRequired ? 0 : Math.min(2000 * 2 ** this.retries, MAX_RECONNECT_DELAY);
                this.retries++;
                this.setState("reconnecting", { reason: lastDisconnect?.error?.message || null });
                await sleep(delay);
                if (!this.stopping && sock === this.sock) {
                    await this.start().catch((error) => this.setState("error", { reason: error.message }));
                }
            }
        }
    }

    async onMessages(sock, { messages, type }) {
        // "notify": new messages; "append": history, and the ones this device sends
        if (type !== "notify") {
            return;
        }
        for (const msg of messages) {
            const item = await messageItem(sock, msg);
            if (!item) {
                continue;
            }
            if (item.has_media) {
                await this.attachFile(sock, msg, item);
            }
            this.notify(this.key, [item]);
        }
    }

    async attachFile(sock, msg, item) {
        if (item.size > MAX_MEDIA_SIZE) {
            item.media_error = TOO_BIG;
            return;
        }
        try {
            const data = await this.download(msg, sock);
            if (data.length > MAX_MEDIA_SIZE) {
                throw new Error(TOO_BIG);
            }
            item.media = { ...fileNameOf(msg, item), data: data.toString("base64") };
        } catch (error) {
            item.media_error = error.message;
        }
    }

    async onUpdates(sock, updates) {
        const items = (await Promise.all(updates.map((update) => statusItem(sock, update)))).filter(Boolean);
        if (items.length) {
            this.notify(this.key, items);
        }
    }

    async onReactions(sock, reactions) {
        const items = (await Promise.all(reactions.map((reaction) => reactionItem(sock, reaction)))).filter(Boolean);
        if (items.length) {
            this.notify(this.key, items);
        }
    }

    /**
     * Send a text, or files with the text as the caption of the first, one
     * message after the other with a pause of a person between two.
     * Resolves to the ids of the messages.
     */
    send(message) {
        const run = this.queue.then(() => this.sendNow(message));
        this.queue = run.catch(() => {});
        return run;
    }

    async sendNow({ to, text = "", files = [], quoted = null }) {
        if (this.state !== "open" || !this.sock) {
            throw new Error("WhatsApp is not linked: scan the QR code in Odoo.");
        }
        if (!text && !files.length) {
            throw new Error("The message is empty.");
        }
        const digits = String(to || "").replace(/\D/g, "");
        if (!/^\d{6,15}$/.test(digits)) {
            throw new Error("The number is not valid.");
        }
        const [found] = (await this.sock.onWhatsApp(digits)) || [];
        if (!found?.exists) {
            throw new Error("This number is not on WhatsApp.");
        }
        const jid = found.jid;
        const { min_gap: min, max_gap: max } = this.config;
        const wait = this.lastSent + min + Math.random() * Math.max(max - min, 0) - Date.now();
        if (wait > 0) {
            await sleep(wait);
        }
        // as a person does: typing, then the message
        await this.sock.sendPresenceUpdate("composing", jid).catch(() => {});
        await sleep(800 + Math.random() * 1200);
        const contents = files.map((file, index) => contentOf(file, index === 0 ? text : ""));
        if (!files.length || (text && !contents[0].caption)) {
            contents.unshift({ text });
        }
        // a reply: the first message quotes the one it answers
        const quote = quoted?.id
            ? { quoted: { key: { remoteJid: jid, id: String(quoted.id), fromMe: Boolean(quoted.from_me) }, message: { conversation: "" } } }
            : {};
        const ids = [];
        for (const [index, content] of contents.entries()) {
            const sent = await this.sock.sendMessage(jid, content, index === 0 ? quote : {});
            ids.push(sent?.key?.id);
        }
        await this.sock.sendPresenceUpdate("paused", jid).catch(() => {});
        this.lastSent = Date.now();
        return ids;
    }

    /**
     * React to a message of the chat of ``to`` (its id; ``from_me`` when it
     * was sent from this number); an empty emoji takes the reaction back. In
     * the line of the messages, without their pause. Resolves to its id.
     */
    react(reaction) {
        const run = this.queue.then(() => this.reactNow(reaction));
        this.queue = run.catch(() => {});
        return run;
    }

    async reactNow({ to, id, from_me: fromMe = false, emoji = "" }) {
        if (this.state !== "open" || !this.sock) {
            throw new Error("WhatsApp is not linked: scan the QR code in Odoo.");
        }
        const digits = String(to || "").replace(/\D/g, "");
        if (!/^\d{6,15}$/.test(digits) || !id || typeof emoji !== "string") {
            throw new Error("The reaction is not valid.");
        }
        const [found] = (await this.sock.onWhatsApp(digits)) || [];
        if (!found?.exists) {
            throw new Error("This number is not on WhatsApp.");
        }
        const key = { remoteJid: found.jid, fromMe: Boolean(fromMe), id: String(id) };
        const sent = await this.sock.sendMessage(found.jid, { react: { text: emoji, key } });
        return sent?.key?.id || null;
    }

    /**
     * The profile picture of ``to``, in base64; null when it shows none (or
     * its privacy settings hide it).
     */
    async picture({ to }) {
        if (this.state !== "open" || !this.sock) {
            throw new Error("WhatsApp is not linked: scan the QR code in Odoo.");
        }
        const digits = String(to || "").replace(/\D/g, "");
        if (!/^\d{6,15}$/.test(digits)) {
            throw new Error("The number is not valid.");
        }
        let url;
        try {
            url = await this.sock.profilePictureUrl(`${digits}@s.whatsapp.net`, "image");
        } catch {
            return null; // none, or hidden
        }
        if (!url) {
            return null;
        }
        const response = await this.fetchPicture(url);
        if (!response.ok) {
            return null;
        }
        const data = Buffer.from(await response.arrayBuffer());
        return data.length && data.length <= MAX_PICTURE_SIZE ? data.toString("base64") : null;
    }

    fetchPicture(url) {
        return fetch(url, { signal: AbortSignal.timeout(10000) });
    }

    /**
     * Messages of the chat of ``to`` read (blue ticks, as the privacy
     * settings of the phone allow) or played (voice messages).
     */
    async receipt({ to, ids = [], kind = "read" }) {
        if (this.state !== "open" || !this.sock) {
            throw new Error("WhatsApp is not linked: scan the QR code in Odoo.");
        }
        const digits = String(to || "").replace(/\D/g, "");
        if (!/^\d{6,15}$/.test(digits) || !ids.length || !["read", "played"].includes(kind)) {
            throw new Error("The receipt is not valid.");
        }
        const jid = `${digits}@s.whatsapp.net`;
        const keys = ids.map((id) => ({ remoteJid: jid, id: String(id), fromMe: false }));
        if (kind === "played") {
            await this.sock.sendReceipts(keys, "played");
        } else {
            await this.sock.readMessages(keys);
        }
    }

    async stop() {
        this.stopping = true;
        this.sock?.end?.(undefined);
        this.sock = null;
        this.setState("stopped");
    }

    async logout() {
        this.stopping = true;
        await this.sock?.logout?.().catch(() => {});
        this.sock = null;
        await rm(path.join(this.folder, "auth"), { recursive: true, force: true });
        this.setState("logged_out", { me: null, qr: null, pairingCode: null, reason: "Unlinked from Odoo." });
    }
}

/** What Baileys sends for a file: a picture, a video, an audio, else a document. */
export function contentOf(file, caption) {
    const data = Buffer.from(file.data, "base64");
    const mimetype = file.mimetype || "application/octet-stream";
    if (["image/jpeg", "image/png"].includes(mimetype)) {
        return { image: data, mimetype, ...(caption ? { caption } : {}) };
    }
    if (mimetype === "video/mp4") {
        return { video: data, mimetype, ...(caption ? { caption } : {}) };
    }
    if (mimetype.startsWith("audio/")) {
        return { audio: data, mimetype };
    }
    return { document: data, mimetype, fileName: file.name || "file", ...(caption ? { caption } : {}) };
}
