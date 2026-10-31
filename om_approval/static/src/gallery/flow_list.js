import { registry } from "@web/core/registry";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";

import { ApprovalGalleryDialog } from "./gallery_dialog";

/** New opens the gallery; a flow opens in the Approval Designer. */
export class ApprovalFlowListController extends ListController {
    async createRecord() {
        // a menu of one app, e.g. HR, offers the templates of its records
        const prefix = this.props.context.approval_gallery_prefix;
        this.env.services.dialog.add(ApprovalGalleryDialog, prefix ? { prefix } : {});
    }

    async openRecord(record) {
        this.actionService.doAction({
            type: "ir.actions.client",
            tag: "om_approval_designer",
            name: record.data.name,
            params: { flow_id: record.resId },
        });
    }
}

registry.category("views").add("approval_flow_list", { ...listView, Controller: ApprovalFlowListController });
