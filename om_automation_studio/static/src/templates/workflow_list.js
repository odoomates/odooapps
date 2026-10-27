import { registry } from "@web/core/registry";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";

import { WorkflowTemplateDialog } from "./template_dialog";

/** New opens the templates; Start from blank, the usual form. */
export class WorkflowListController extends ListController {
    async createRecord(params) {
        this.env.services.dialog.add(WorkflowTemplateDialog, {
            onBlank: () => super.createRecord(params),
        });
    }
}

registry.category("views").add("om_workflow_list", { ...listView, Controller: WorkflowListController });
