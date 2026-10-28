/** @odoo-module **/

import { Component, useEffect, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";

const MODEL = "om.workflow.approval";
// the models a workflow asks approvals about, read once per page
let approvalModels = null;

/**
 * At the top of the form of a record that waits for an approval: who it
 * waits for, what it blocks, and for the approver the buttons to answer.
 */
export class WorkflowApprovalBanner extends Component {
    static template = "om_automation_studio.ApprovalBanner";
    static props = { record: Object };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ approvals: [], busy: false });
        // again after each save: the save may be what asks the approval
        useEffect(
            (resModel, resId, dirty) => {
                if (!dirty) {
                    this.load(resModel, resId);
                }
            },
            () => [this.props.record.resModel, this.props.record.resId, this.props.record.isDirty]
        );
    }

    async load(resModel, resId) {
        if (!resId) {
            this.state.approvals = [];
            return;
        }
        approvalModels ||= this.orm.call(MODEL, "get_approval_models", []);
        const models = await approvalModels;
        this.state.approvals = models.includes(resModel)
            ? await this.orm.call(MODEL, "get_pending", [resModel, resId])
            : [];
    }

    async decide(approval, method) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        const record = this.props.record;
        try {
            if (!(await record.save())) {
                return;
            }
            await this.orm.call(MODEL, method, [[approval.id]]);
            this.notification.add(method === "action_approve" ? _t("Approved.") : _t("Rejected."), {
                type: method === "action_approve" ? "success" : "warning",
            });
            await record.load();
            record.model.notify();
            await this.load(record.resModel, record.resId);
        } finally {
            this.state.busy = false;
        }
    }

    open(approval) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: MODEL,
            res_id: approval.id,
            views: [[false, "form"]],
        });
    }
}

FormController.components = { ...FormController.components, WorkflowApprovalBanner };
