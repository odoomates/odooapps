/** @odoo-module **/

import { Component, onWillRender, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { sprintf } from "@web/core/utils/strings";
import { FormController } from "@web/views/form/form_controller";

const MODEL = "approval.request";
// the models having a button flow, read once per page
let approvalModels = null;

/**
 * The values of a form record as last read from the server. The form view of Odoo 16 keeps its records in the
 * legacy BasicModel, which reads them anew, in a new object, on each load and each save, and keeps the changes
 * apart: so the banner sees the record read again, e.g. once a button ran.
 */
function serverValues(record) {
    const datapoint = record.model.__bm__ && record.model.__bm__.localData[record.__bm_handle__];
    return datapoint ? datapoint.data : null;
}

/**
 * At the top of the form of a record whose button waits for an approval: who it waits for and whether the record
 * is locked, with Approve and Refuse for the approvers, Withdraw for the requester and Unlock for the managers.
 * A locked record shows read-only.
 */
export class ApprovalBanner extends Component {
    static template = "om_approval.ApprovalBanner";
    static props = { record: Object, canEdit: { type: Boolean, optional: true } };
    static defaultProps = { canEdit: true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = useState({ requests: [], locked: false, busy: false, expanded: {} });
        // the record this banner made read-only, to make it editable again once unlocked
        this.lockedRecord = null;
        // the record and its values read from the server, the approvals were loaded for
        this.loadedFor = null;
        // the form renders on each change of its record: the approvals are read again for another record, and
        // after each save and each reload, as a button may have asked an approval
        onWillRender(() => {
            const record = this.props.record;
            const values = serverValues(record);
            const loaded = this.loadedFor;
            if ((!loaded || loaded.record !== record || loaded.values !== values) && !record.isDirty) {
                this.loadedFor = { record, values };
                this.load(record.resModel, record.resId);
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
        if (data.locked && record.isInEdition && !record.isDirty) {
            this.lockedRecord = record;
            await record.switchMode("readonly");
        } else if (!data.locked && this.lockedRecord === record && this.props.canEdit) {
            this.lockedRecord = null;
            await record.switchMode("edit");
        }
    }

    async reload() {
        const record = this.props.record;
        // the chatter reads its messages again as the form renders
        await record.load();
        record.model.notify();
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
            body: sprintf(_t("Withdraw %s? The record is no longer waiting for it, and becomes editable again."),
                          request.name),
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
            return "fa-ban";
        }
        return request.locking ? "fa-lock" : "fa-hourglass-half";
    }
}

FormController.components = { ...FormController.components, ApprovalBanner };
