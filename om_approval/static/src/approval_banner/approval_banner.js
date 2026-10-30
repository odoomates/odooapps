import { Component, proxy, t, useEffect, useProps } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

const MODEL = "approval.request";
// the models having a button flow, read once per page
let approvalModels = null;

/**
 * At the top of the form of a record whose button waits for an approval: who it waits for and whether the record
 * is locked, with Approve and Refuse for the approvers, Withdraw for the requester and Unlock for the managers.
 * A locked record shows read-only.
 */
export class ApprovalBanner extends Component {
    static template = "om_approval.ApprovalBanner";
    props = useProps({ record: t.object(), canEdit: t.boolean().optional(true) });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = proxy({ requests: [], locked: false, busy: false, expanded: {} });
        // the record this banner made read-only, to make it editable again once unlocked
        this.lockedRecord = null;
        useEffect(() => {
            // again after each save and each reload: a button may have asked an approval
            const { resModel, resId, dirty } = this.props.record;
            if (!dirty) {
                this.load(resModel, resId);
            }
        });
    }

    async load(resModel, resId) {
        let data = { locked: false, requests: [] };
        if (resId) {
            approvalModels ||= this.orm.call(MODEL, "get_approval_models", []);
            if ((await approvalModels).includes(resModel)) {
                data = await this.orm.call(MODEL, "get_record_approvals", [resModel, resId]);
            }
        }
        const record = this.props.record;
        if (record.resModel !== resModel || record.resId !== resId) {
            return; // another record opened meanwhile
        }
        this.state.requests = data.requests;
        this.state.locked = data.locked;
        if (data.locked && record.isInEdition && !record.dirty) {
            this.lockedRecord = record;
            await record.switchMode("readonly");
        } else if (!data.locked && this.lockedRecord === record && this.props.canEdit) {
            this.lockedRecord = null;
            await record.switchMode("edit");
        }
    }

    async reload() {
        const record = this.props.record;
        await record.load();
        this.env.bus.trigger("MAIL:RELOAD-THREAD", { model: record.resModel, id: record.resId });
        await this.load(record.resModel, record.resId);
    }

    async call(request, method, message) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call(MODEL, method, [[request.id]]);
            if (message) {
                this.notification.add(message, { type: "success" });
            }
            await this.reload();
        } finally {
            this.state.busy = false;
        }
    }

    async approve(request) {
        await this.decide(request, "action_open_approve", _t("Approved."));
    }

    async refuse(request) {
        await this.decide(request, "action_open_refuse", _t("Refused."));
    }

    /** Approve or refuse: at once, or in the dialog asking the note when the flow asks for one. */
    async decide(request, method, message) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const result = await this.orm.call(MODEL, method, [[request.id]]);
            if (result && typeof result === "object") {
                await this.action.doAction(result, { onClose: () => this.reload() });
            } else {
                this.notification.add(message, { type: "success" });
                await this.reload();
            }
        } finally {
            this.state.busy = false;
        }
    }

    dismiss(request) {
        return this.call(request, "action_dismiss_refusal");
    }

    attachmentUrl(attachment) {
        return `/web/content/${attachment.id}?download=true`;
    }

    withdraw(request) {
        this.dialog.add(ConfirmationDialog, {
            body: _t("Withdraw %s? The record is no longer waiting for it, and becomes editable again.", request.name),
            confirmLabel: _t("Withdraw"),
            confirm: () => this.call(request, "action_cancel", _t("Withdrawn.")),
            cancel: () => {},
        });
    }

    unlock(request) {
        this.dialog.add(ConfirmationDialog, {
            body: _t("Unlock the record? It becomes editable again."),
            confirmLabel: _t("Unlock"),
            confirm: () => this.call(request, "action_unlock", _t("Unlocked.")),
            cancel: () => {},
        });
    }

    toggle(request) {
        this.state.expanded[request.id] = !this.state.expanded[request.id];
    }

    open(request) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: MODEL,
            res_id: request.id,
            views: [[false, "form"]],
        });
    }

    alertClass(request) {
        if (request.state === "to_approve") {
            return "alert-warning";
        }
        if (request.state === "refused") {
            return "alert-danger";
        }
        return request.state === "approved" ? "alert-success" : "alert-secondary";
    }

    icon(request) {
        if (request.state === "refused") {
            return "block";
        }
        return request.locking ? "lock" : "hourglass_empty";
    }
}

patch(FormController, {
    components: { ...FormController.components, ApprovalBanner },
});
