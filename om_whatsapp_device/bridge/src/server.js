// The WhatsApp Bridge of om_whatsapp_device: keeps the WhatsApp linked devices of the
// accounts of Odoo connected, and talks to Odoo over HTTP.
//
//   Odoo -> bridge: this API, on 127.0.0.1, with the secret in
//                    Authorization: Bearer <secret>
//   bridge -> Odoo: POST of what comes in to the webhook of the account, the
//                    body signed in X-Signature-256: sha256=<hmac of the secret>
//
// Configuration, from the environment:
//   OM_WA_SECRET  the secret shared with Odoo (required)
//   OM_WA_PORT    default 8077
//   OM_WA_HOST    default 127.0.0.1: keep it on this machine
//   OM_WA_DATA    where the keys of the linked devices are kept, default ./data
import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import { readdir } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Session } from "./session.js";

export const VERSION = "1.0.0";
const MAX_BODY = 40 * 1024 * 1024;
const WEBHOOK_TRIES = 6;

export const quietLogger = {
    level: "warn",
    child() {
        return this;
    },
    trace() {},
    debug() {},
    info() {},
    warn(...args) {
        console.warn("[whatsapp]", ...args);
    },
    error(...args) {
        console.error("[whatsapp]", ...args);
    },
};

function sameSecret(given, secret) {
    const a = createHash("sha256").update(String(given || "")).digest();
    const b = createHash("sha256").update(String(secret)).digest();
    return timingSafeEqual(a, b);
}

/** Hand items to the webhook of a session, signed, again on failure. */
export function makeNotifier({ secret, sessions, fetchImpl = fetch, logger = quietLogger, delays = [1, 2, 5, 15, 60] }) {
    return function notify(key, items) {
        const session = sessions.get(key);
        const url = session?.config.webhook_url;
        if (!url) {
            return Promise.resolve(false);
        }
        const body = JSON.stringify({ key, items });
        const signature = `sha256=${createHmac("sha256", secret).update(body).digest("hex")}`;
        const headers = { "Content-Type": "application/json", "X-Signature-256": signature };
        // the database of the account: Odoo serves several from one address
        if (session.config.database) {
            headers["X-Odoo-Database"] = session.config.database;
        }
        const attempt = async (tries) => {
            try {
                const response = await fetchImpl(url, {
                    method: "POST",
                    headers,
                    body,
                });
                if (response.ok) {
                    return true;
                }
                throw new Error(`Odoo answered ${response.status}`);
            } catch (error) {
                if (tries + 1 >= WEBHOOK_TRIES) {
                    logger.error(`${key}: ${items.length} item(s) not handed to Odoo: ${error.message}`);
                    return false;
                }
                await new Promise((resolve) => setTimeout(resolve, (delays[tries] ?? 60) * 1000));
                return attempt(tries + 1);
            }
        };
        return attempt(0);
    };
}

async function readJson(request) {
    let size = 0;
    const chunks = [];
    for await (const chunk of request) {
        size += chunk.length;
        if (size > MAX_BODY) {
            throw Object.assign(new Error("Too big"), { status: 413 });
        }
        chunks.push(chunk);
    }
    if (!chunks.length) {
        return {};
    }
    try {
        return JSON.parse(Buffer.concat(chunks).toString("utf8"));
    } catch {
        throw Object.assign(new Error("Not JSON"), { status: 400 });
    }
}

/** The HTTP API, over the sessions. */
export function createApp({ secret, dataDir, createSocket, loadAuth, download, notifyFactory = makeNotifier, logger = quietLogger }) {
    const sessions = new Map();
    const notify = notifyFactory({ secret, sessions, logger });
    const sessionOf = (key) => {
        if (!/^[A-Za-z0-9_-]{8,64}$/.test(key)) {
            throw Object.assign(new Error("Bad session key"), { status: 400 });
        }
        if (!sessions.has(key)) {
            sessions.set(key, new Session(key, { dataDir, createSocket, loadAuth, notify, logger, download }));
        }
        return sessions.get(key);
    };

    const routes = {
        "GET /health": async () => ({ ok: true, version: VERSION, sessions: [...sessions.values()].map((s) => s.status) }),
        "GET /sessions/:key": async (key) => ({ ok: true, ...sessionOf(key).status }),
        "POST /sessions/:key/start": async (key, body) => {
            const session = sessionOf(key);
            await session.saveConfig({
                webhook_url: body.webhook_url,
                database: body.database || null,
                min_gap: Number(body.min_gap ?? 2000),
                max_gap: Number(body.max_gap ?? 6000),
                pairing_phone: body.pairing_phone ? String(body.pairing_phone).replace(/\D/g, "") : null,
            });
            if (["stopped", "logged_out", "error"].includes(session.state) || body.restart) {
                await session.stop();
                await session.start();
            }
            return { ok: true, ...session.status };
        },
        "POST /sessions/:key/send": async (key, body) => ({ ok: true, ids: await sessionOf(key).send(body) }),
        "POST /sessions/:key/react": async (key, body) => ({ ok: true, id: await sessionOf(key).react(body) }),
        "POST /sessions/:key/picture": async (key, body) => ({ ok: true, data: await sessionOf(key).picture(body) }),
        "POST /sessions/:key/receipt": async (key, body) => {
            await sessionOf(key).receipt(body);
            return { ok: true };
        },
        "POST /sessions/:key/stop": async (key) => {
            await sessionOf(key).stop();
            return { ok: true };
        },
        "POST /sessions/:key/logout": async (key) => {
            await sessionOf(key).logout();
            return { ok: true };
        },
    };

    async function handle(request, response) {
        let status = 200;
        let answer;
        try {
            if (!sameSecret((request.headers.authorization || "").replace(/^Bearer /, ""), secret)) {
                throw Object.assign(new Error("Forbidden"), { status: 403 });
            }
            const url = new URL(request.url, "http://bridge");
            const parts = url.pathname.split("/").filter(Boolean);
            const route = parts[0] === "sessions" && parts[1]
                ? `${request.method} /sessions/:key${parts[2] ? `/${parts[2]}` : ""}`
                : `${request.method} /${parts.join("/")}`;
            const run = routes[route];
            if (!run) {
                throw Object.assign(new Error("Not found"), { status: 404 });
            }
            answer = await run(parts[1], request.method === "POST" ? await readJson(request) : {});
        } catch (error) {
            status = error.status || 200;
            answer = { ok: false, error: error.message };
        }
        response.writeHead(status, { "Content-Type": "application/json" });
        response.end(JSON.stringify(answer));
    }

    /** The linked sessions of before a restart connect again. */
    async function resume() {
        let keys = [];
        try {
            keys = await readdir(dataDir);
        } catch {
            return;
        }
        for (const key of keys) {
            const session = sessionOf(key);
            if (await session.loadConfig()) {
                await session.start().catch((error) => logger.error(`${key}: ${error.message}`));
            }
        }
    }

    return { handle, resume, sessions };
}

/** A real socket of Baileys. */
async function baileys() {
    const { default: makeWASocket, Browsers, fetchLatestBaileysVersion, useMultiFileAuthState } = await import(
        "@whiskeysockets/baileys"
    );
    let version;
    try {
        ({ version } = await fetchLatestBaileysVersion());
    } catch {
        version = undefined; // the one of the library
    }
    return {
        loadAuth: useMultiFileAuthState,
        createSocket: (auth, logger) =>
            makeWASocket({
                auth,
                logger,
                ...(version ? { version } : {}),
                browser: Browsers.ubuntu("Odoo"),
                // the phone keeps its notifications
                markOnlineOnConnect: false,
                // the recent history only: Baileys learns from it which hidden ids (@lid) are which numbers.
                // Odoo gets none of it: the session hands over the new messages only ("notify")
                syncFullHistory: false,
            }),
    };
}

async function main() {
    // the keys of the linked devices: files of this user only, whoever starts it
    process.umask(0o077);
    const secret = process.env.OM_WA_SECRET;
    if (!secret || secret.length < 16) {
        console.error("Set OM_WA_SECRET, the secret of the WhatsApp Bridge shown in Odoo (16 characters at least).");
        process.exit(1);
    }
    const host = process.env.OM_WA_HOST || "127.0.0.1";
    const port = Number(process.env.OM_WA_PORT || 8077);
    const dataDir = path.resolve(process.env.OM_WA_DATA || "data");
    const app = createApp({ secret, dataDir, ...(await baileys()) });
    http.createServer(app.handle).listen(port, host, () => {
        console.log(`WhatsApp Bridge ${VERSION} on http://${host}:${port}, data in ${dataDir}`);
    });
    await app.resume();
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
    main();
}
