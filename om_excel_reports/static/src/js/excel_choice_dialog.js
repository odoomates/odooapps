import { Component, onMounted, signal, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

/**
 * "Print <report>" chooser: PDF, Excel, both, or a preview in a new tab.
 * Esc (handled by the Dialog) cancels; the Excel tile is focused so Enter picks it.
 */
export class ExcelChoiceDialog extends Component {
    static template = "om_excel_reports.ExcelChoiceDialog";
    static components = { Dialog };
    props = useProps({
        title: t.string(),
        onChoice: t.function(),
        close: t.function(),
    });
    primary = signal.ref();

    setup() {
        onMounted(() => this.primary()?.focus());
    }

    choose(choice) {
        this.props.onChoice(choice);
        this.props.close();
    }
}
