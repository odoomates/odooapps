/** @odoo-module **/
// The buttons of the list of profiles that need no selection: Odoo 16 shows
// the header buttons of a list only once records are selected.
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";

export class AccessProfileListController extends ListController {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    openWizard(xmlid) {
        return this.actionService.doAction(xmlid, { onClose: () => this.model.load() });
    }
}

registry.category("views").add("om_access_profile_list", {
    ...listView,
    Controller: AccessProfileListController,
    buttonTemplate: "om_access_manager.ProfileListView.Buttons",
});
