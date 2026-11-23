import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/**
 * Shown instead of running a button that still needs an approval: who has to
 * approve, what they decided, and the buttons to approve, reject or ask.
 */
export class PenApprovalAction extends Component {
    static template = "om_pen.ApprovalAction";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.params = this.props.action.params;
        this.state = proxy({ status: null });
        onWillStart(() => this.load());
    }

    async load() {
        const { model, res_id, button_name, button_type } = this.params;
        this.state.status = await this.orm.call("om.pen.approval.rule", "approval_status", [
            model,
            res_id,
            button_name,
            button_type,
        ]);
    }

    get allApproved() {
        return this.state.status?.rules.every((rule) => rule.state === "approved");
    }

    async decide(rule, approved) {
        await this.orm.call("om.pen.approval.rule", "approval_decide", [rule.id, this.params.res_id, approved]);
        await this.load();
    }

    async ask(rule) {
        await this.orm.call("om.pen.approval.rule", "approval_request", [rule.id, this.params.res_id]);
        this.notification.add(`${rule.approver} has been asked.`, { type: "success" });
    }

    close() {
        this.action.doAction({ type: "ir.actions.act_window_close" });
    }
}

registry.category("actions").add("om_pen.approval", PenApprovalAction);
