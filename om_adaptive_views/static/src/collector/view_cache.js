import { rpcBus } from "@web/core/network/rpc";

const CHANGES = ["action_apply", "action_undo", "action_dismiss"];

/**
 * Applying or undoing a change rebuilds the views on the server, but this browser keeps
 * the views it already loaded. Drop them, as Odoo does when a view is edited, so the
 * change shows on the very next screen. Other users get it from their next load on.
 */
rpcBus.addEventListener("RPC:RESPONSE", (ev) => {
    const params = ev.detail.data?.params || {};
    if (params.model === "om.adapt.rule" && CHANGES.includes(params.method) && !ev.detail.error) {
        rpcBus.trigger("CLEAR-CACHES", "get_views");
    }
});
