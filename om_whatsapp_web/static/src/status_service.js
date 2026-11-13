import { reactive } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { getExtensionInfo, getStatus, onStatusWake, openWhatsappTab } from "./extension_bridge";

const ACCOUNT = "om.whatsapp.account";
const CHECK_DELAY = 30000;
// the server is told the same status at most this often (it records the last connection)
const SERVER_DELAY = 60000;

/**
 * The status of WhatsApp Web in this browser, from the ping of the extension
 * (``info``), its status (``page``) and the account of the linked number
 * (``account``, from the server):
 *
 * - level: "connected" (green), "connecting" (amber), "disconnected" (red),
 *   "unknown" (grey: an extension too old to tell)
 * - reason: what to tell the user
 * - action: "open" when opening WhatsApp Web fixes it, else "check"
 * - blocking: whether a message sent now would not go, or go from another number
 */
export function describeStatus(info, page, account) {
    if (!info) {
        return {
            level: "disconnected",
            reason: _t(
                "The Odoo Mates WhatsApp Connector extension does not answer on this page: install it, or click its icon and Allow this Odoo."
            ),
            action: "check",
            blocking: true,
        };
    }
    if (!info.features.includes("status")) {
        return {
            level: "unknown",
            reason: _t("Update the Odoo Mates WhatsApp Connector extension (1.5.0 or later) to see the connection here."),
            action: "check",
            blocking: false,
        };
    }
    if (!page?.ok) {
        return { level: "unknown", reason: _t("The extension did not tell the status of WhatsApp Web."), action: "check", blocking: false };
    }
    if (!page.tab) {
        return {
            level: "disconnected",
            reason: _t("WhatsApp Web is not open in this browser: the replies come to Odoo once it is open. Sending opens it."),
            action: "open",
            blocking: false,
        };
    }
    if (page.state === "loading") {
        return { level: "connecting", reason: _t("WhatsApp Web is loading..."), action: "open", blocking: false };
    }
    if (page.state === "qr") {
        return {
            level: "disconnected",
            reason: _t("WhatsApp Web is not linked: open it and scan the QR code with your phone."),
            action: "open",
            blocking: true,
        };
    }
    if (page.reader === false) {
        return {
            level: "disconnected",
            reason: page.error || _t("The messages of WhatsApp Web cannot be read: update the extension."),
            action: "check",
            blocking: false,
        };
    }
    if (page.me && !account) {
        return {
            level: "disconnected",
            reason: _t(
                "The WhatsApp linked in this browser (+%(number)s) is not the number of your WhatsApp Web account.",
                { number: page.me }
            ),
            action: "open",
            blocking: true,
        };
    }
    return {
        level: "connected",
        reason: account
            ? _t("Connected: %(account)s, +%(number)s", { account: account.name, number: page.me })
            : _t("Connected to WhatsApp Web."),
        action: null,
        blocking: false,
    };
}

/** The status of WhatsApp Web in this browser, shared by the dots of every view. */
export const whatsappStatus = reactive({
    ready: false,
    hasAccount: false,
    level: "unknown",
    reason: "",
    action: null,
    blocking: false,
    me: null,
    accountId: null,
    accountName: null,
    checking: false,
});

/**
 * Keeps ``whatsappStatus`` up to date in the pages of the users of WhatsApp:
 * when the extension says it changed (a tab closed, a phone linked...), and
 * every CHECK_DELAY while the page is seen.
 */
export const whatsappStatusService = {
    dependencies: ["orm"],
    start(env, { orm }) {
        let told = { me: undefined, at: 0, answer: null };
        const tellServer = async (me) => {
            if (told.answer && told.me === me && Date.now() - told.at < SERVER_DELAY) {
                return told.answer;
            }
            const answer = await orm.silent.call(ACCOUNT, "om_whatsapp_web_status", [me || false]);
            told = { me, at: Date.now(), answer };
            return answer;
        };
        let running = null;
        const refresh = () => {
            running ??= (async () => {
                whatsappStatus.checking = true;
                try {
                    const info = await getExtensionInfo();
                    const page = info?.features.includes("status") ? await getStatus().catch(() => null) : null;
                    const me = page?.tab && page.state === "ready" ? page.me || null : null;
                    const answer = await tellServer(me);
                    Object.assign(whatsappStatus, describeStatus(info, page, answer.account), {
                        ready: true,
                        hasAccount: answer.has_account,
                        me,
                        accountId: answer.account?.id || null,
                        accountName: answer.account?.name || null,
                    });
                } catch (error) {
                    console.warn("WhatsApp Web status not checked:", error);
                } finally {
                    whatsappStatus.checking = false;
                }
            })().finally(() => (running = null));
            return running;
        };
        const openWhatsapp = async () => {
            await openWhatsappTab().catch(() => {});
            setTimeout(refresh, 1500);
        };
        user.hasGroup("om_whatsapp_base.group_om_whatsapp_user").then((allowed) => {
            if (!allowed) {
                return;
            }
            onStatusWake(refresh);
            setInterval(() => document.visibilityState === "visible" && refresh(), CHECK_DELAY);
            document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && refresh());
            setTimeout(refresh, 1500);
        });
        return { state: whatsappStatus, refresh, openWhatsapp };
    },
};

registry.category("services").add("om_whatsapp_web_status", whatsappStatusService);
