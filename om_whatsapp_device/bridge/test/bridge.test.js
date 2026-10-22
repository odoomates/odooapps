// The WhatsApp Bridge against a fake WhatsApp: a socket that emits what Baileys
// emits, and records what it is asked.
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { EventEmitter } from "node:events";
import { mkdtemp, rm, stat } from "node:fs/promises";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, beforeEach, test } from "node:test";
import { DisconnectReason } from "@whiskeysockets/baileys";
import { Readable } from "node:stream";
import { createApp, makeNotifier, quietLogger } from "../src/server.js";
import { readLimited } from "../src/session.js";

const SECRET = "a-secret-of-the-bridge";
const KEY = "account-key-123";
const ME = "32470000000";

class FakeSocket {
    constructor(auth) {
        this.ev = new EventEmitter();
        this.auth = auth;
        this.sent = [];
        this.presences = [];
        this.user = null;
        this.signalRepository = { lidMapping: { getPNForLID: async (lid) => (lid === "98765@lid" ? "32470555555@s.whatsapp.net" : null) } };
    }
    async onWhatsApp(number) {
        return number === "32470999999" ? [{ exists: false }] : [{ exists: true, jid: `${number}@s.whatsapp.net` }];
    }
    async sendMessage(jid, content, options = {}) {
        this.sent.push({ jid, content, ...(options.quoted ? { quoted: options.quoted } : {}) });
        return { key: { id: `OUT${this.sent.length}`, remoteJid: jid, fromMe: true } };
    }
    async sendPresenceUpdate(type, jid) {
        this.presences.push([type, jid]);
    }
    async requestPairingCode(phone) {
        return `CODE-${phone.slice(-4)}`;
    }
    async logout() {}
    end() {}
    // what WhatsApp does
    link() {
        this.user = { id: `${ME}:12@s.whatsapp.net` };
        this.ev.emit("connection.update", { connection: "open" });
    }
    receive(messages, type = "notify") {
        this.ev.emit("messages.upsert", { messages, type });
    }
}

let dataDir;
let sockets;
let received;
let server;
let base;
let app;

const tick = () => new Promise((resolve) => setTimeout(resolve, 20));

/** The status of a session once ``check`` holds of it, or the last one after 3 s. */
async function statusWhen(key, check) {
    let status;
    for (let i = 0; i < 150; i++) {
        status = await call("GET", `/sessions/${key}`);
        if (check(status)) {
            break;
        }
        await tick();
    }
    return status;
}

function call(method, url, body, secret = SECRET) {
    return new Promise((resolve, reject) => {
        const request = http.request(`${base}${url}`, {
            method,
            headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/json" },
        }, (response) => {
            let data = "";
            response.on("data", (chunk) => (data += chunk));
            response.on("end", () => resolve({ status: response.statusCode, ...JSON.parse(data) }));
        });
        request.on("error", reject);
        request.end(body ? JSON.stringify(body) : undefined);
    });
}

before(async () => {
    dataDir = await mkdtemp(path.join(tmpdir(), "om-wa-bridge-"));
    sockets = [];
    app = createApp({
        secret: SECRET,
        dataDir,
        logger: quietLogger,
        loadAuth: async () => ({ state: { creds: {} }, saveCreds: async () => {} }),
        createSocket: (auth) => {
            const sock = new FakeSocket(auth);
            sockets.push(sock);
            return sock;
        },
        download: async () => Buffer.from("%PDF-1.4"),
        // what reaches Odoo, at once
        notifyFactory: () => (key, items) => {
            received.push(...items.map((item) => ({ key, ...item })));
            return Promise.resolve(true);
        },
    });
    server = http.createServer(app.handle);
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    base = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
    server.close();
    await rm(dataDir, { recursive: true, force: true });
});

beforeEach(() => {
    received = [];
});

const sock = () => sockets.at(-1);
const items = (kind) => received.filter((item) => item.kind === kind);

test("only Odoo, with the secret, talks to it", async () => {
    assert.equal((await call("GET", "/health", null, "wrong")).status, 403);
    const health = await call("GET", "/health");
    assert.equal(health.ok, true);
    assert.equal((await call("GET", "/nothing")).status, 404);
    assert.equal((await call("POST", "/sessions/bad key!/start", {})).status, 400);
});

test("a QR code, then linked by the phone", async () => {
    let status = await call("POST", `/sessions/${KEY}/start`, { webhook_url: "http://odoo/webhook", min_gap: 0, max_gap: 0 });
    assert.equal(status.state, "starting");
    sock().ev.emit("connection.update", { qr: "2@QRDATA" });
    status = await statusWhen(KEY, (s) => s.state === "qr");
    assert.equal(status.state, "qr");
    assert.equal(status.qr, "2@QRDATA");
    assert.match(status.qr_image, /^data:image\/png;base64,/);
    sock().link();
    await tick();
    status = await call("GET", `/sessions/${KEY}`);
    assert.deepEqual([status.state, status.me, status.qr], ["open", ME, null]);
    assert.equal(items("state").at(-1).state, "open");
});

test("messages come to Odoo; groups, status and history do not", async () => {
    const s = sock();
    s.receive([
        { key: { id: "IN1", remoteJid: "32470123456@s.whatsapp.net" }, pushName: "Alice", message: { conversation: "Is it ready?" }, messageTimestamp: 1760000000 },
        { key: { id: "IN2", remoteJid: "98765@lid" }, message: { extendedTextMessage: { text: "Hidden number", contextInfo: { stanzaId: "OUT1" } } } },
        { key: { id: "IN3", remoteJid: "98765@lid", remoteJidAlt: "32470666666@s.whatsapp.net" }, message: { conversation: "Alt" } },
        { key: { id: "IN4", remoteJid: "120363@g.us", participant: "32470123456@s.whatsapp.net" }, message: { conversation: "Group" } },
        { key: { id: "IN5", remoteJid: "status@broadcast" }, message: { conversation: "Status" } },
        { key: { id: "IN6", remoteJid: "32470123456@s.whatsapp.net" }, message: { documentMessage: { mimetype: "application/pdf", fileName: "plan.pdf", caption: "The plan", fileLength: 8 } } },
        { key: { id: "IN7", remoteJid: "32470123456@s.whatsapp.net" }, message: { audioMessage: { mimetype: "audio/ogg; codecs=opus", ptt: true, fileLength: 8 } } },
        { key: { id: "IN8", remoteJid: "32470123456@s.whatsapp.net", fromMe: true }, message: { conversation: "Typed on the phone" } },
        { key: { id: "IN9", remoteJid: "32470123456@s.whatsapp.net" }, message: { locationMessage: { degreesLatitude: 29.37, degreesLongitude: 47.97, name: "Office" } } },
    ]);
    s.receive([{ key: { id: "OLD", remoteJid: "32470123456@s.whatsapp.net" }, message: { conversation: "History" } }], "append");
    await tick();
    const messages = items("message");
    assert.deepEqual(messages.map((m) => m.id), ["IN1", "IN2", "IN3", "IN6", "IN7", "IN8", "IN9"]);
    const [text, lid, alt, file, voice, mine, location] = messages;
    assert.deepEqual([text.phone, text.body, text.name, text.type], ["32470123456", "Is it ready?", "Alice", "chat"]);
    assert.deepEqual([lid.phone, lid.quoted_id], ["32470555555", "OUT1"]);
    assert.equal(alt.phone, "32470666666");
    assert.deepEqual([file.type, file.body, file.media.name, file.media.mimetype], ["document", "The plan", "plan.pdf", "application/pdf"]);
    assert.equal(Buffer.from(file.media.data, "base64").toString(), "%PDF-1.4");
    assert.deepEqual([voice.type, voice.media.name], ["ptt", "voice-message-IN7.ogg"]);
    assert.deepEqual([mine.from_me, mine.name], [true, null]);
    assert.equal(location.note, "Location");
    assert.match(location.body, /Office https:\/\/maps\.google\.com\/\?q=29\.37,47\.97/);
});

test("a file too big comes without it", async () => {
    sock().receive([{ key: { id: "BIG", remoteJid: "32470123456@s.whatsapp.net" }, message: { videoMessage: { mimetype: "video/mp4", fileLength: 40 * 1024 * 1024 } } }]);
    await tick();
    const [big] = items("message");
    assert.equal(big.media, undefined);
    assert.equal(big.media_error, "The file is too big.");
});

test("ticks and reactions", async () => {
    sock().ev.emit("messages.update", [
        { key: { id: "OUT1", remoteJid: "32470123456@s.whatsapp.net", fromMe: true }, update: { status: 3 } },
        { key: { id: "OUT1", remoteJid: "32470123456@s.whatsapp.net", fromMe: true }, update: { status: 4 } },
        { key: { id: "IN1", remoteJid: "32470123456@s.whatsapp.net", fromMe: false }, update: { status: 4 } },
    ]);
    sock().ev.emit("messages.reaction", [
        { key: { id: "OUT1", remoteJid: "32470123456@s.whatsapp.net", fromMe: true }, reaction: { text: "👍", key: { fromMe: false } } },
        { key: { id: "IN1", remoteJid: "32470123456@s.whatsapp.net" }, reaction: { text: "", key: { fromMe: true } } },
    ]);
    await tick();
    assert.deepEqual(items("status").map((s) => s.status), ["delivered", "read"]);
    assert.deepEqual(items("reaction").map((r) => [r.message_id, r.emoji, r.from_me]), [["OUT1", "👍", false], ["IN1", "", true]]);
});

test("send: text, files with the caption, typing first, one at a time", async () => {
    const s = sock();
    const text = await call("POST", `/sessions/${KEY}/send`, { to: "+32 470 12 34 56", text: "Yes, tomorrow" });
    assert.deepEqual(text.ids, ["OUT1"]);
    assert.deepEqual(s.sent[0], { jid: "32470123456@s.whatsapp.net", content: { text: "Yes, tomorrow" } });
    assert.deepEqual(s.presences.slice(0, 2).map(([type]) => type), ["composing", "paused"]);
    const files = await call("POST", `/sessions/${KEY}/send`, {
        to: "32470123456",
        text: "Your quotation",
        files: [
            { name: "S00042.pdf", mimetype: "application/pdf", data: Buffer.from("%PDF").toString("base64") },
            { name: "photo.jpg", mimetype: "image/jpeg", data: Buffer.from("jpg").toString("base64") },
        ],
    });
    assert.deepEqual(files.ids, ["OUT2", "OUT3"]);
    assert.equal(s.sent[1].content.fileName, "S00042.pdf");
    assert.equal(s.sent[1].content.caption, "Your quotation");
    assert.ok(Buffer.isBuffer(s.sent[2].content.image));
    assert.equal(s.sent[2].content.caption, undefined);
    const absent = await call("POST", `/sessions/${KEY}/send`, { to: "32470999999", text: "Hi" });
    assert.deepEqual([absent.ok, absent.error], [false, "This number is not on WhatsApp."]);
    const empty = await call("POST", `/sessions/${KEY}/send`, { to: "32470123456" });
    assert.equal(empty.error, "The message is empty.");
});

test("react: to a message received or sent, taken back with no emoji", async () => {
    const s = sock();
    const added = await call("POST", `/sessions/${KEY}/react`, { to: "+32 470 12 34 56", id: "IN1", from_me: false, emoji: "👍" });
    assert.equal(added.ok, true);
    assert.deepEqual(s.sent.at(-1), {
        jid: "32470123456@s.whatsapp.net",
        content: { react: { text: "👍", key: { remoteJid: "32470123456@s.whatsapp.net", fromMe: false, id: "IN1" } } },
    });
    await call("POST", `/sessions/${KEY}/react`, { to: "32470123456", id: "OUT1", from_me: true, emoji: "" });
    assert.deepEqual(s.sent.at(-1).content.react, { text: "", key: { remoteJid: "32470123456@s.whatsapp.net", fromMe: true, id: "OUT1" } });
    const absent = await call("POST", `/sessions/${KEY}/react`, { to: "32470999999", id: "IN1", emoji: "👍" });
    assert.equal(absent.error, "This number is not on WhatsApp.");
    const invalid = await call("POST", `/sessions/${KEY}/react`, { to: "32470123456", emoji: "👍" });
    assert.equal(invalid.error, "The reaction is not valid.");
});

test("receipts: read with the privacy of the phone, played for voice messages", async () => {
    const s = sock();
    s.read = [];
    s.receipts = [];
    s.readMessages = async (keys) => s.read.push(keys);
    s.sendReceipts = async (keys, type) => s.receipts.push([keys, type]);
    await call("POST", `/sessions/${KEY}/receipt`, { to: "+32 470 12 34 56", ids: ["IN1", "IN2"], kind: "read" });
    assert.deepEqual(s.read, [[
        { remoteJid: "32470123456@s.whatsapp.net", id: "IN1", fromMe: false },
        { remoteJid: "32470123456@s.whatsapp.net", id: "IN2", fromMe: false },
    ]]);
    await call("POST", `/sessions/${KEY}/receipt`, { to: "32470123456", ids: ["IN3"], kind: "played" });
    assert.deepEqual(s.receipts, [[[{ remoteJid: "32470123456@s.whatsapp.net", id: "IN3", fromMe: false }], "played"]]);
    const invalid = await call("POST", `/sessions/${KEY}/receipt`, { to: "32470123456", ids: [], kind: "read" });
    assert.equal(invalid.error, "The receipt is not valid.");
});

test("picture: read and sent, none when hidden", async () => {
    const s = sock();
    const session = app.sessions.get(KEY);
    s.profilePictureUrl = async (jid) => {
        if (jid !== "32470123456@s.whatsapp.net") throw new Error("item-not-found");
        return "https://pps.whatsapp.net/v/photo.jpg";
    };
    session.fetchPicture = async () => ({ ok: true, arrayBuffer: async () => new TextEncoder().encode("JPEG").buffer });
    const shown = await call("POST", `/sessions/${KEY}/picture`, { to: "+32 470 12 34 56" });
    assert.equal(Buffer.from(shown.data, "base64").toString(), "JPEG");
    const hidden = await call("POST", `/sessions/${KEY}/picture`, { to: "32470999999" });
    assert.deepEqual([hidden.ok, hidden.data], [true, null]);
});

test("send: a reply quotes the message it answers, on its first message", async () => {
    const s = sock();
    await call("POST", `/sessions/${KEY}/send`, { to: "32470123456", text: "Yes, Friday", quoted: { id: "IN5", from_me: false } });
    assert.deepEqual(s.sent.at(-1).quoted.key, { remoteJid: "32470123456@s.whatsapp.net", id: "IN5", fromMe: false });
    await call("POST", `/sessions/${KEY}/send`, { to: "32470123456", text: "plain" });
    assert.equal(s.sent.at(-1).quoted, undefined);
});

test("the pause of a person between two messages", async () => {
    const session = app.sessions.get(KEY);
    session.config.min_gap = 300;
    session.config.max_gap = 300;
    const started = Date.now();
    await Promise.all([
        call("POST", `/sessions/${KEY}/send`, { to: "32470123456", text: "one" }),
        call("POST", `/sessions/${KEY}/send`, { to: "32470123456", text: "two" }),
    ]);
    // the second waits for the first, and its pause
    assert.ok(Date.now() - started >= 300);
    assert.deepEqual(sock().sent.slice(-2).map((m) => m.content.text), ["one", "two"]);
    session.config.min_gap = 0;
    session.config.max_gap = 0;
});

test("unlinked from the phone: logged out, the keys removed", async () => {
    const authFolder = path.join(dataDir, KEY, "auth");
    sock().ev.emit("connection.update", { connection: "close", lastDisconnect: { error: { output: { statusCode: DisconnectReason.loggedOut } } } });
    await tick();
    const status = await call("GET", `/sessions/${KEY}`);
    assert.equal(status.state, "logged_out");
    await assert.rejects(stat(authFolder));
    const send = await call("POST", `/sessions/${KEY}/send`, { to: "32470123456", text: "Hi" });
    assert.match(send.error, /not linked/);
});

test("a pairing code instead of the QR code", async () => {
    const key = "account-key-pairing";
    await call("POST", `/sessions/${key}/start`, { webhook_url: "http://odoo/webhook", pairing_phone: "+965 5555 1234" });
    sock().ev.emit("connection.update", { qr: "2@QR" });
    await tick();
    const status = await call("GET", `/sessions/${key}`);
    assert.deepEqual([status.state, status.pairing_code, status.qr], ["pairing", "CODE-1234", null]);
});

test("the webhook of Odoo: signed, and tried again", async () => {
    const calls = [];
    const sessions = new Map([[KEY, { config: { webhook_url: "http://odoo/webhook", database: "wa_db" } }]]);
    let failures = 2;
    const fetchImpl = async (url, options) => {
        calls.push(options);
        return { ok: failures-- <= 0, status: 503 };
    };
    const notify = makeNotifier({ secret: SECRET, sessions, fetchImpl, delays: [0, 0, 0], logger: quietLogger });
    assert.equal(await notify(KEY, [{ kind: "status", id: "OUT1", status: "read" }]), true);
    assert.equal(calls.length, 3);
    const { body, headers } = calls[0];
    assert.deepEqual(JSON.parse(body), { key: KEY, items: [{ kind: "status", id: "OUT1", status: "read" }] });
    assert.equal(headers["X-Signature-256"], `sha256=${createHmac("sha256", SECRET).update(body).digest("hex")}`);
    assert.equal(headers["X-Odoo-Database"], "wa_db");
});

test("a file is not read past the limit, whatever size its sender gave", async () => {
    let read = 0;
    const chunks = function* () {
        for (let i = 0; i < 1000; i++) {
            read++;
            yield Buffer.alloc(1024);
        }
    };
    await assert.rejects(readLimited(Readable.from(chunks()), 10 * 1024), /too big/);
    assert.ok(read <= 11);
    const small = await readLimited(Readable.from([Buffer.from("%PDF"), Buffer.from("-1.4")]), 10 * 1024);
    assert.equal(small.toString(), "%PDF-1.4");
});
