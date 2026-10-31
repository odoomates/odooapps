/** @odoo-module **/

import { Component } from "@odoo/owl";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

import { ApprovalGalleryDialog } from "./gallery_dialog";

/** Set up an approval, from the Action menu (the gear) of a form, for the approval managers. */
export class SetUpApproval extends Component {
    static template = "om_approval.SetUpApproval";
    static components = { DropdownItem };
    static props = { resModel: String };

    setup() {
        this.dialog = useService("dialog");
    }

    open() {
        this.dialog.add(ApprovalGalleryDialog, { model: this.props.resModel });
    }
}

registry.category("action_menus").add("om-approval-set-up", {
    Component: SetUpApproval,
    // the props of the item, or nothing to hide it: on a form, for the approval managers
    getProps: async (props, env) => {
        if (env.config?.viewType !== "form" || !props.resModel || env.inDialog) {
            return null;
        }
        if (!(await env.services.user.hasGroup("om_approval.group_approval_manager"))) {
            return null;
        }
        return { resModel: props.resModel };
    },
});
