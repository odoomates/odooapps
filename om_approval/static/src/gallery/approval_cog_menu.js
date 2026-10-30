import { Component } from "@odoo/owl";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { ACTIONS_GROUP_NUMBER } from "@web/search/action_menus/action_menus";

import { ApprovalGalleryDialog } from "./gallery_dialog";

/** Set up an approval, from the gear menu of a form, for the approval managers. */
export class SetUpApproval extends Component {
    static template = "om_approval.SetUpApproval";
    static components = { DropdownItem };

    setup() {
        this.dialog = useService("dialog");
    }

    open() {
        this.dialog.add(ApprovalGalleryDialog, { model: this.env.model.root.resModel });
    }
}

registry.category("cogMenu").add("om-approval-set-up", {
    Component: SetUpApproval,
    groupNumber: ACTIONS_GROUP_NUMBER,
    isDisplayed: async (env) =>
        env.config?.viewType === "form" &&
        Boolean(env.model?.root?.resModel) &&
        !env.inDialog &&
        (await user.hasGroup("om_approval.group_approval_manager")),
});
