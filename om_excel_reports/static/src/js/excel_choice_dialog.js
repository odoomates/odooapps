/** @odoo-module **/
import { Component, onMounted, useRef } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

/**
 * "Print <report>" chooser: PDF, Excel, both, or a preview in a new tab.
 * Esc (handled by the Dialog) cancels; the Excel tile is focused so Enter picks it.
 */
export class ExcelChoiceDialog extends Component {
    static template = "om_excel_reports.ExcelChoiceDialog";
    static components = { Dialog };
    static props = {
        title: String,
        onChoice: Function,
        close: Function,
    };

    setup() {
        this.primary = useRef("primary");
        onMounted(() => this.primary.el?.focus());
    }

    choose(choice) {
        this.props.onChoice(choice);
        this.props.close();
    }
}
