import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network/rpc";
import { session } from "@web/session";

const URL = "/om_adaptive_views/collect";
const FLUSH_MS = 60_000;

/**
 * Counts how screens are used and sends the counts in batches.
 *
 * Only the name of what was used is kept - a field, a filter, a column - never a value.
 * Counts of the same thing add up in the browser, so a busy page sends one line per
 * thing, once a minute, and a last batch when the tab is hidden or closed.
 */
const buffer = new Map();
let timer = null;

export function isLearning() {
    return Boolean(session.om_adaptive_learning);
}

export function count(event, model, { element = "", viewId = 0, actionId = 0 } = {}) {
    if (!isLearning() || !model) {
        return;
    }
    const entry = {
        event,
        model,
        element: element || "",
        view_id: Number.isInteger(viewId) ? viewId : 0,
        action_id: Number.isInteger(actionId) ? actionId : 0,
    };
    const key = JSON.stringify(entry);
    buffer.set(key, (buffer.get(key) || 0) + 1);
    if (!timer) {
        timer = browser.setTimeout(flush, FLUSH_MS);
    }
}

function takeBatch() {
    const events = [...buffer].map(([key, n]) => ({ ...JSON.parse(key), count: n }));
    buffer.clear();
    if (timer) {
        browser.clearTimeout(timer);
        timer = null;
    }
    return events;
}

export async function flush() {
    const events = takeBatch();
    if (events.length) {
        try {
            await rpc(URL, { events }, { silent: true });
        } catch {
            // counts are a hint, not data: losing a batch is fine
        }
    }
}

// the page is going away - the tab hidden, closed or reloaded: hand the last batch to the
// browser, which sends it even after the page is gone
function sendLastBatch() {
    if (!buffer.size) {
        return;
    }
    const body = JSON.stringify({ jsonrpc: "2.0", method: "call", params: { events: takeBatch() } });
    browser.navigator.sendBeacon?.(URL, new Blob([body], { type: "application/json" }));
}

browser.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
        sendLastBatch();
    }
});
browser.addEventListener("pagehide", sendLastBatch);
