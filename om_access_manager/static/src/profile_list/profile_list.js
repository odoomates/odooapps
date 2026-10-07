/** @odoo-module **/
// The buttons of the list of profiles that need no selection: Odoo 15 shows
// the header buttons of a list only once records are selected.
import { _t } from "@web/core/l10n/translation";
import ListController from "web.ListController";
import ListView from "web.ListView";
import viewRegistry from "web.view_registry";

const AccessProfileListController = ListController.extend({
    renderButtons() {
        this._super(...arguments);
        if (!this.$buttons) {
            return;
        }
        const $template = $('<button type="button" class="btn btn-secondary o_om_access_template"/>')
            .text(_t("New from Template"))
            .on("click", () => this._omOpenWizard("om_access_manager.om_access_template_wizard_action"));
        const $import = $('<button type="button" class="btn btn-secondary o_om_access_import"/>')
            .text(_t("Import"))
            .on("click", () => this._omOpenWizard("om_access_manager.om_access_import_action"));
        this.$buttons.find(".o_list_button_add").after($template, $import);
    },

    _omOpenWizard(xmlid) {
        return this.do_action(xmlid, { on_close: () => this.reload() });
    },
});

viewRegistry.add("om_access_profile_list", ListView.extend({
    config: Object.assign({}, ListView.prototype.config, { Controller: AccessProfileListController }),
}));
